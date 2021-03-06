# coding=utf8
"""
Controllers for Kata.
"""
from cgi import FieldStorage
import datetime
import httplib
import json
import logging
import mimetypes
import string
import urllib2
from urllib import urlencode, unquote
import difflib
import time
from Crypto.Cipher import Blowfish
import base64

import functionally as fn
import rdflib
import re
import sqlalchemy
from lxml import etree
from paste.deploy.converters import asbool
from pylons import config, request, session, g
from pylons.decorators.cache import beaker_cache
from pylons.i18n import _
import os

from ckan.controllers.api import ApiController
from ckan.controllers.package import PackageController
from ckan.controllers.user import UserController
from ckan.controllers.storage import StorageController
from ckan.controllers.home import HomeController
import ckan.lib.i18n
from ckan.lib.base import BaseController, c, h, redirect, render, abort
from ckan.lib.email_notifications import send_notification
from ckan.lib import captcha, helpers, search
import ckan.lib.maintain as maintain
from ckan.logic import get_action, NotAuthorized, NotFound, ValidationError
import ckan.logic as logic
import ckan.model as model
from ckan.model import Package
import ckan.plugins as plugins
from ckan.common import response
from ckan.common import OrderedDict
import ckan.plugins as p

import ckanext.harvest.interfaces as h_interfaces
import ckanext.kata.clamd_wrapper as clamd_wrapper
import ckanext.kata.settings as settings
from ckanext.kata.schemas import Schemas as kata_schemas
from ckanext.kata import utils

_get_or_bust = ckan.logic.get_or_bust
check_access = logic.check_access

log = logging.getLogger(__name__)
t = plugins.toolkit


def get_package_owner(package):
    """Returns the user id of the package admin for the specified package.
       Package creator is always admin, so return their id. Package
       may also have other admins.

       :param package: package data
       :type package: Package object
       :returns: userid
       :rtype: string
    """
    return package.creator_user_id


def _encode_params(params):
    return [(k, v.encode('utf-8') if isinstance(v, basestring) else str(v))
            for k, v in params]


def url_with_params(url, params):
    params = _encode_params(params)
    return url + u'?' + urlencode(params)


class MetadataController(BaseController):
    '''
    URN export
    '''
    XMLNS = "urn:nbn:se:uu:ub:epc-schema:rs-location-mapping"

    def _urnexport(self):
        '''
        Uncached urnexport, needed for testing.
        '''
        _or_ = sqlalchemy.or_
        _and_ = sqlalchemy.and_

        xsi = "http://www.w3.org/2001/XMLSchema-instance"
        schemalocation = "urn:nbn:se:uu:ub:epc-schema:rs-location-mapping " \
                         "http://urn.kb.se/resolve?urn=urn:nbn:se:uu:ub:epc-schema:rs-location-mapping&godirectly"
        records = etree.Element("{" + self.XMLNS + "}records",
                         attrib={"{" + xsi + "}schemaLocation": schemalocation},
                         nsmap={'xsi': xsi, None: self.XMLNS})

        # Query for all rows whose EITHER key = pids_x_id with corresponding value containing a Kata/IDA PID OR
        # key = pids_x_type with correspondig value being 'primary'. type index (between the underscores) is used
        # for finding out the corresponding id index for primary id
        query = model.Session.query(model.PackageExtra, model.Package).filter(_or_(_and_(model.PackageExtra.key.like('pids_%_id'), model.PackageExtra.value.like('urn:nbn:fi:csc-%')), _and_(model.PackageExtra.key.like('pids_%_type'), model.PackageExtra.value.like('primary')))). \
            join(model.Package).filter(model.Package.private == False).filter(_or_(model.Package.state == 'active', model.Package.state == 'deleted')). \
            values('package_id', 'name', 'key', 'value')

        # Group stuff according to package ids

        # List of all package ids that are included in the query (since all datasets must have at least one pid,
        # all published datasets' id's should be present)
        package_ids = list()
        # Pid ids grouped by package_id
        package_grouped_pids = dict()
        # Primary PID indices grouped by package_id
        package_grouped_primary_pid_indices = dict()
        # Package names grouped by package_id
        package_grouped_names = dict()

        for package_id, name, key, value in query:
            if package_id not in package_ids:
                package_ids.append(package_id)
            if not package_id in package_grouped_names:
                package_grouped_names[package_id] = name
            if key.endswith('_id'):
                package_grouped_pids.setdefault(package_id, {}).update({key: value})
            if key.endswith('_type') and not package_id in package_grouped_primary_pid_indices:
                package_grouped_primary_pid_indices[package_id] = key[key.find('_')+1:key.rfind('_')]

        prot = etree.SubElement(records, self._locns('protocol-version'))
        prot.text = '3.0'
        datestmp = etree.SubElement(records, self._locns('datestamp'), attrib={'type': 'modified'})
        now = datetime.datetime.now().isoformat()
        datestmp.text = now
        base_url = config.get('ckan.site_url', '').strip("/")

        # Iterate over all package_ids
        for package_id in package_ids:
            name = package_grouped_names[package_id]
            primary_idx = -1
            primary_pid = None
            if package_id in package_grouped_primary_pid_indices:
                primary_idx = package_grouped_primary_pid_indices[package_id]
            if primary_idx != -1 and package_id in package_grouped_pids:
                primary_pid_id_key = 'pids_' + primary_idx + '_id'
                if primary_pid_id_key in package_grouped_pids[package_id]:
                    primary_pid = package_grouped_pids[package_id][primary_pid_id_key]

            # Create one urnexport entry anyways for the package_id
            self._create_urnexport_xml_item(records, package_id, name, base_url, now)
            # If primary pid is not the same as package_id (but according to previous must be ida or kata type)
            # create one urnexport entry for that too
            if primary_pid and primary_pid != package_id:
                self._create_urnexport_xml_item(records, primary_pid, name, base_url, now)

        response.content_type = 'application/xml; charset=utf-8'
        return etree.tostring(records, encoding="UTF-8")

    def _locns(self, loc):
        return "{%s}%s" % (self.XMLNS, loc)

    def _create_urnexport_xml_item(self, records, identifier_text, name, base_url, now):
        record = etree.SubElement(records, self._locns('record'))
        header = etree.SubElement(record, self._locns('header'))
        datestmp = etree.SubElement(header, self._locns('datestamp'), attrib={'type': 'modified'})
        datestmp.text = now
        identifier = etree.SubElement(header, self._locns('identifier'))
        identifier.text = identifier_text

        destinations = etree.SubElement(header, self._locns('destinations'))
        destination = etree.SubElement(destinations, self._locns('destination'), attrib={'status': 'activated'})
        etree.SubElement(destination, self._locns('datestamp'), attrib={'type': 'activated'})

        url = etree.SubElement(destination, self._locns('url'))
        url.text = "%s%s" % (base_url,
            helpers.url_for(controller='package',
                   action='read',
                   id=name))

    @beaker_cache(type="dbm", expire=86400)
    def urnexport(self):
        '''
        Generate an XML listing of packages, which have Kata or Ida URN as data PID.
        Used by a third party service.

        :returns: An XML listing of packages and their URNs
        :rtype: string (xml)
        '''
        return self._urnexport()


class KATAApiController(ApiController):
    '''
    Functions for autocomplete fields in add dataset form
    '''

    @beaker_cache(type="dbm", expire=30, invalidate_on_startup=True)
    def _get_funders(self):
        records = model.Session.execute("select distinct second.value from package_extra as first \
            left join package_extra as second on first.package_id = second.package_id and second.key =  'agent_' || substring(first.key from 'agent_(.*)_role') || '_organisation' \
            where first.key like 'agent%role' and first.value = 'funder' and first.state='active'")
        url = config.get("ckanext.kata.funder_url", None) or "file://%s" % os.path.abspath(os.path.join(os.path.dirname(__file__), "theme/public/funder.json"))
        source = urllib2.urlopen(url)
        try:
            return ["%s - %s" % (funder['fi'], funder['en']) for funder in json.load(source)] + [result[0] for result in records]
        finally:
            source.close()

    def funder_autocomplete(self):
        query = request.params.get('incomplete', '').lower()
        limit = request.params.get('limit', 10)

        matches = sorted([funder for funder in self._get_funders() if funder and string.find(funder.lower(), query) != -1],
                         key=lambda match: (match.lower().startswith(query), difflib.SequenceMatcher(None, match.lower(), query).ratio()),
                         reverse=True)[0:limit]
        resultSet = {
            'ResultSet': {
                'Result': [{'Name': tag} for tag in matches]
            }
        }
        return self._finish_ok(resultSet)

    def media_type_autocomplete(self):
        '''
        Suggestions for mimetype

        :rtype: dictionary
        '''
        query = request.params.get('incomplete', '')
        known_types = set(mimetypes.types_map.values())
        matches = [ type_label for type_label in known_types if string.find(type_label, query) != -1 ]
        matches = sorted(matches)
        result_set = {
            'ResultSet': {
                'Result': [{'Name': label} for label in matches]
            }
        }
        return self._finish_ok(result_set)

    def tag_autocomplete(self):
        '''
        Suggestions for tags (keywords)

        :rtype: dictionary
        '''

        query = request.params.get('incomplete', '')
        language = request.params.get('language', '')

        return self._onki_autocomplete_uri(query, "koko", language)

    def discipline_autocomplete(self):
        '''
        Suggestions for discipline

        :rtype: dictionary
        '''

        query = request.params.get('incomplete', '')
        language = request.params.get('language', '')

        return self._onki_autocomplete_uri(query, "okm-tieteenala", language)

    def location_autocomplete(self):
        '''
        Suggestions for spatial coverage

        :rtype: dictionary
        '''
        query = request.params.get('incomplete', '')

        return self._onki_autocomplete(query, "paikat")

    def _query_finto(self, query, vocab, language=None):
        '''
        Queries Finto ontologies by returning the whole result set, which can
        be parsed according to the needs (see _onki_autocomplete_uri)

        :param query: the string to search for
        :type query: string
        :param vocab: the vocabulary/ontology, i.e. lexvo
        :type vocab: string
        :param language: the language of the query
        :type query: string

        :rtype: dictionary
        '''

        url_template = "http://dev.finto.fi/rest/v1/search?query={q}*&vocab={v}" if vocab == 'paikat' else "http://api.finto.fi/rest/v1/search?query={q}*&vocab={v}"

        if language:
            url_template += "&lang={l}"

        jsondata = {}

        if query:
            try:
                url = url_template.format(q=query, v=vocab, l=language)
            except UnicodeEncodeError:
                url = url_template.format(q=query.encode('utf-8'), v=vocab, l=language)

            try:
                data = urllib2.urlopen(url).read()
            except (urllib2.HTTPError, urllib2.URLError, httplib.HTTPException):
                return None

            jsondata = json.loads(data)

        return jsondata

    def _onki_autocomplete(self, query, vocab, language=None):
        '''
        Queries the remote ontology for suggestions and
        formats the data.

        :param query: the string to search for
        :type query: string
        :param vocab: the vocabulary/ontology
        :type vocab: string
        :param language: the language of the query
        :type query: string

        :rtype: dictionary
        '''
        jsondata = self._query_finto(query, vocab, language)
        labels = []

        if jsondata and u'results' in jsondata:
            results = jsondata['results']
            labels = [concept.get('prefLabel', '').encode('utf-8') for concept in results]

        result_set = {
            'ResultSet': {
                'Result': [{'Name': label} for label in labels]
            }
        }

        return self._finish_ok(result_set)

    def _onki_autocomplete_uri(self, query, vocab, language=None):
        '''
        Queries the remote ontology for suggestions and
        formats the data, suggests uri's. Returns uri as key and
        label as name.

        :param query: the string to search for
        :type query: string
        :param vocab: the vocabulary/ontology
        :type vocab: string
        :param language: the language of the query
        :type query: string

        :rtype: dictionary
        '''

        jsondata = self._query_finto(query, vocab, language)
        labels = []

        if jsondata and u'results' in jsondata:
            results = jsondata['results']
            labels = [(concept.get('prefLabel', '').encode('utf-8'),
                       concept['uri'].encode('utf-8')) for concept in results]

        result_set = [{'key': l[1], 'label': l[0], 'name': l[0]} for l in labels]

        return self._finish_ok(result_set)

    def language_autocomplete(self):
        '''
        Suggestions for languages.

        :rtype: dictionary
        '''

        language = request.params.get('language', '')
        query = request.params.get('incomplete', '')

        jsondata = self._query_finto(query, "lexvo", language)
        labels = []

        if jsondata and u'results' in jsondata:
            results = jsondata['results']
            labels = [(concept.get('prefLabel', '').encode('utf-8'),
                       concept.get('localname', '').encode('utf-8')) for concept in results]

        result_set = [{'key': l[1], 'label': l[0], 'name': l[0]} for l in labels]

        return self._finish_ok(result_set)


    def pkg_organization_autocomplete(self):
        query = request.params.get('incomplete', '').encode('utf-8')
        data = get_action('organization_autocomplete')({'user': c.user}, {'q': query})

        return self._finish_ok(data)


class ContactController(BaseController):
    """
    Add features to contact the dataset's owner.

    From the web page, this can be seen from the link telling that this dataset is accessible by contacting the author.
    The feature provides a form for message sending, and the message is sent via email.
    """
    def __init__(self):
        if config.get('kata.bf') and len(config.get('kata.bf')) > 4 and len(config.get('kata.bf')) < 56:
            self.crypto = Blowfish.new('config.get("kata.bf")')
        else:
            log.info('No encryption key (kata.bf) is set, falling back to beaker.session.secret!')
            self.crypto = Blowfish.new('config.get("beaker.session.secret")')

    def _pad(self, encr_str):
        return encr_str + ' ' * (8 - (len(encr_str) % 8))

    def _get_logged_in_user(self):
        if c.userobj:
            name = c.userobj.fullname if c.userobj.fullname else c.userobj.name
            email = c.userobj.email
            return {'name': name, 'email': email}
        else:
            return None

    def _get_contact_email(self, pkg_id, contact_id):
        recipient = None
        if contact_id:
            contacts = utils.get_package_contacts(pkg_id)
            contact = fn.first(filter(lambda c: c.get('id') == contact_id, contacts))

            if contact and 'email' in contact.keys():
                email = contact.get('email')
                name = contact.get('name')
                recipient = {'name': name, 'email': email}

        return recipient

    def _send_message(self, subject, message, recipient_email, recipient_name=None):
        email_dict = {'subject': subject,
                      'body': message}

        if not recipient_name:
            # fall back to using the email address as the name of the recipient
            recipient_name = recipient_email

        recipient_dict = {'display_name': recipient_name, 'email': recipient_email}

        if message:
            send_notification(recipient_dict, email_dict)

    def _prepare_and_send(self, pkg_id, recipient_id, subject, prefix_template, suffix):
        """
        Sends a message by email from the logged in user to the appropriate
        contact address of the given dataset.

        The prefix template should have formatting placeholders for the following arguments:
        {sender_name}, {sender_email}, {package_title}, {package_id}

        :param pkg_id: package id
        :type pkg_id: string
        :param recipient_id: id of the recipient, as returned by utils.get_package_contacts
        :type recipient_id: string
        :param subject: the subject of the message
        :type subject: string
        :param prefix_template: the template for the prefix to be automatically included before the user message
        :type prefix_template: unicode
        :param suffix: an additional note to be automatically included after the user message
        :type suffix: unicode
        """

        url = h.url_for(controller='package', action='read', id=pkg_id)

        if asbool(config.get('kata.contact_captcha')):
            try:
                captcha.check_recaptcha(request)
            except captcha.CaptchaError:
                h.flash_error(_(u'Bad Captcha. Please try again.'))
                redirect(url)

        if not request.params.get('accept_logging'):
            h.flash_error(_(u"Message not sent as logging wasn't permitted"))
            return redirect(url)

        if asbool(config.get('kata.disable_contact')):
            h.flash_error(_(u"Sending contact emails is prohibited for now. Please try again later or contact customer "
u"service."))
            return redirect(url)

        package = Package.get(pkg_id)
        package_title = package.title if package.title else package.name

        sender_addr = request.params.get('from_address')
        sender_name = request.params.get('from_name')
        recipient = self._get_contact_email(pkg_id, recipient_id)

        if not recipient:
            abort(404, _('Recipient not found'))

        user_msg = request.params.get('msg', '')

        if request.params.get('hp'):
            h.flash_error(_(u"Message not sent. Couldn't confirm human interaction (spam bot control)"))
            return redirect(url)

        if sender_addr and sender_name and \
                isinstance(sender_name, basestring) and len(sender_name) >= 3:
            if user_msg:
                prefix = prefix_template.format(
                    sender_name=sender_name,
                    sender_email=sender_addr,
                    package_title=package_title,
                    package_id=pkg_id
                    # above line was: metadata_pid=utils.get_primary_data_pid_from_package(package)
                )

                log.info(u"Message {m} sent from {a} ({b}) to {r} about {c}, IP: {d}"
                         .format(m=user_msg, a=sender_name, b=sender_addr, r=recipient, c=pkg_id,
                                 d=request.environ.get('REMOTE_ADDR', 'No remote address')))

                full_msg = u"{a}{b}{c}".format(a=prefix, b=user_msg, c=suffix)
                self._send_message(subject, full_msg, recipient.get('email'), recipient.get('name'))
                h.flash_success(_(u"Message sent"))
            else:
                h.flash_error(_(u"No message"))
        else:
            h.flash_error(_(u"Message not sent. Please, provide reply address and name. Name must contain \
at least three letters."))

        return redirect(url)

    def send_contact_message(self, pkg_id):
        """
        Sends a message by email from the logged in user to the appropriate
        contact address of the dataset.

        :param pkg_id: package id
        :type pkg_id: string
        """

        package = Package.get(pkg_id)
        if not package:
            ckan.lib.base.abort(404, _("Dataset not found"))

        package_title = package.title if package.title else package.name
        subject = u"Message regarding dataset / Viesti koskien tietoaineistoa %s" % package_title
        recipient_id = request.params.get('recipient', '')
        return self._prepare_and_send(pkg_id, recipient_id, subject, settings.USER_MESSAGE_PREFIX_TEMPLATE, settings.REPLY_TO_SENDER_NOTE)


    def send_request_message(self, pkg_id):
        """
        Sends a data request message by email from the logged in user to the appropriate
        contact address of the dataset.

        :param pkg_id: package id
        :type pkg_id: string
        """

        package = Package.get(pkg_id)
        package_title = package.title if package.title else package.name
        subject = u"Data access request for dataset / Datapyyntö tietoaineistolle %s" % package_title
        recipient_id = request.params.get('recipient', '')

        return self._prepare_and_send(pkg_id, recipient_id, subject, settings.DATA_REQUEST_PREFIX_TEMPLATE, settings.REPLY_TO_SENDER_NOTE)

    def render_contact_form(self, pkg_id):
        """
        Render the contact form if allowed.

        :param pkg_id: package id
        :type pkg_id: string
        """

        c.package = Package.get(pkg_id)

        if not c.package:
            abort(404, _(u"Dataset not found"))

        if asbool(config.get('kata.disable_contact')):
            h.flash_error(_(u"Sending contact emails is prohibited for now. "
                            u"Please try again later or contact customer service."))

            return redirect(h.url_for(controller='package',
                                      action="read",
                                      id=c.package.name))

        contacts = utils.get_package_contacts(c.package.id)
        c.recipient_options = []
        for contact in contacts:
            if 'name' in contact:
                text_val = contact['name']
            else:
                at_idx = contact['email'].find('@')
                text_val = contact['email'][0:at_idx]
                text_val = text_val.replace(".", " ").title()
                print(text_val)

            c.recipient_options.append({'text': text_val, 'value': contact['id']})

        c.recipient_index = request.params.get('recipient', '')
        c.current_time = base64.b64encode(self.crypto.encrypt(self._pad(str(int(time.time())))))
        return render('contact/contact_form.html')

    def render_request_form(self, pkg_id):
        """
        Render the access request contact form if allowed.

        :param pkg_id: package id
        :type pkg_id: string
        """
        c.package = Package.get(pkg_id)

        if not c.package:
            abort(404, _(u"Dataset not found"))

        if asbool(config.get('kata.disable_contact')):
            h.flash_error(_(u"Sending contact emails is prohibited for now. "
                            u"Please try again later or contact customer service."))

            return redirect(h.url_for(controller='package',
                                      action="read",
                                      id=c.package.name))

        contacts = utils.get_package_contacts(c.package.id)
        c.recipient_options = [{'text': contact['name'], 'value': contact['id']} for contact in contacts]
        c.recipient_index = request.params.get('recipient', '')
        c.current_time = base64.b64encode(self.crypto.encrypt(self._pad(str(int(time.time())))))

        return render('contact/dataset_request_form.html')


class KataUserController(UserController):
    """
    Overwrite logged_in function in the super class.
    """

    def logged_in(self):
        """Minor rewrite to redirect the user to the own profile page instead of
        the dashboard.
        """
        # we need to set the language via a redirect
        lang = session.pop('lang', None)
        session.save()
        came_from = request.params.get('came_from', '')
        if came_from and not came_from.isspace():
            came_from = came_from\
                        .replace('\n', ' ')\
                        .replace('\r', '')


        # we need to set the language explicitly here or the flash
        # messages will not be translated.
        ckan.lib.i18n.set_lang(lang)

        if h.url_is_local(came_from):
            return h.redirect_to(unquote(str(came_from)))

        if c.user:
            context = {'model': model,
                       'user': c.user}

            data_dict = {'id': c.user}

            user_dict = get_action('user_show')(context, data_dict)

            #h.flash_success(_("%s is now logged in") %
            #                user_dict['display_name'])
            return h.redirect_to(controller='user', action='read', id=c.userobj.name)
        else:
            err = _('Login failed. Bad username or password.')
            if asbool(config.get('ckan.legacy_templates', 'false')):
                h.flash_error(err)
                h.redirect_to(controller='user',
                              action='login', came_from=came_from)
            else:
                return self.login(error=err)

    def logged_out_page(self):
        """ Redirect user to front page and inform user. """
        if not c.user:
            h.flash_notice(_("Successfully logged out."))
        h.redirect_to(controller='home', action='index')


class KataPackageController(PackageController):
    """
    Dataset handling modifications and additions.
    """

    def _upload_xml(self, errors=None, error_summary=None):
        '''
        Allow filling dataset form by parsing a user uploaded metadata file.
        '''
        context = {'model': model, 'session': model.Session,
                   'user': c.user or c.author}
        try:
            t.check_access('package_create', context)
        except t.NotAuthorized:
            t.abort(401, _('Unauthorized to upload metadata'))

        xmlfile = u''
        field_storage = request.params.get('xmlfile')
        if isinstance(field_storage, FieldStorage):
            bffr = field_storage.file
            xmlfile = bffr.read()
        url = request.params.get('url', u'')
        xmltype = request.params.get('xml-format', u'')
        log.info('Importing from {src}'.format(
            src='file: ' + field_storage.filename if field_storage else 'url: ' + url))
        for harvester in plugins.PluginImplementations(h_interfaces.IHarvester):
            info = harvester.info()
            if not info or 'name' not in info:
                log.error('Harvester %r does not provide the harvester name in the info response' % str(harvester))
                continue
            if xmltype == info['name']:
                log.debug('_upload_xml: Found harvester for import: {nam}'.format(nam=info['name']))
                try:
                    if xmlfile:
                        pkg_dict = harvester.parse_xml(xmlfile, context)
                    elif url:
                        pkg_dict = harvester.fetch_xml(url, context)
                    else:
                        h.flash_error(_('Give upload URL or file.'))
                        return h.redirect_to(controller='package', action='new')
                    return super(KataPackageController, self).new(pkg_dict, errors, error_summary)
                except (urllib2.URLError, urllib2.HTTPError):
                    log.debug('Could not fetch from url {ur}'.format(ur=url))
                    h.flash_error(_('Could not fetch from url {ur}'.format(ur=url)))
                except ValueError, e:
                    log.debug(e)
                    h.flash_error(_('Invalid upload URL'))
                except etree.XMLSyntaxError:
                    h.flash_error(_('Invalid XML content'))
                except Exception, e:
                    log.debug(e)
                    log.debug(type(e))
                    h.flash_error(_("Failed to load file"))
                return h.redirect_to(controller='package', action='new') # on error

    def new(self, data=None, errors=None, error_summary=None):
        '''
        Overwrite CKAN method to take uploading xml into sequence.
        '''

        if request.params.get('upload'):
            return self._upload_xml(errors, error_summary)
        else:
            return super(KataPackageController, self).new(data, errors, error_summary)


    def browse(self):
        '''
        List datasets, code is mostly the same as package search.
        '''
        from ckan.lib.search import SearchError
        package_type = 'dataset'

        # default to discipline
        c.facet_choose_title = request.params.get('facet_choose_title') or 'extras_discipline'
        c.facet_choose_item = request.params.get('facet_choose_item')

        try:
            context = {'model': model, 'user': c.user or c.author}
            check_access('site_read', context)
        except NotAuthorized:
            abort(401, _('Not authorized to see this page'))

        q = c.q = u''
        c.query_error = False
        try:
            page = int(request.params.get('page', 1))
        except ValueError, e:
            abort(400, ('"page" parameter must be an integer'))

        limit = 50

        params_nopage = [(k, v) for k, v in request.params.items()
                         if k != 'page']

        def remove_field(key, value=None, replace=None):
            return h.remove_url_param(key, value=value, replace=replace,
                                      controller='ckanext.kata.controllers:KataPackageController', action='browse')

        c.remove_field = remove_field

        sort_by = request.params.get('sort', None)

        params_nosort = [(k, v) for k, v in params_nopage if k != 'sort']

        def _sort_by(fields):
            """
            Sort by the given list of fields.

            Each entry in the list is a 2-tuple: (fieldname, sort_order)

            eg - [('metadata_modified', 'desc'), ('name', 'asc')]

            If fields is empty, then the default ordering is used.
            """
            params = params_nosort[:]

            if fields:
                sort_string = ', '.join('%s %s' % f for f in fields)
                params.append(('sort', sort_string))
            return url_with_params(h.url_for(controller='ckanext.kata.controllers:KataPackageController', action='browse'), params)

        c.sort_by = _sort_by
        if sort_by is None:
            c.sort_by_fields = []
        else:
            c.sort_by_fields = [field.split()[0]
                                for field in sort_by.split(',')]

        def pager_url(q=None, page=None):
            params = list(params_nopage)
            params.append(('page', page))
            return url_with_params(h.url_for(controller='ckanext.kata.controllers:KataPackageController', action='browse'), params)

        c.search_url_params = urlencode(_encode_params(params_nopage))

        try:
            c.fields = []
            # c.fields_grouped will contain a dict of params containing
            # a list of values eg {'tags':['tag1', 'tag2']}
            c.fields_grouped = {}
            search_extras = {}
            fq = ''

            if c.facet_choose_item:
                # Build query: in dataset browsing the query is limited to a single facet only
                fq = ' %s:"%s"' % (c.facet_choose_title, c.facet_choose_item)
                c.fields.append((c.facet_choose_title, c.facet_choose_item))
                c.fields_grouped[c.facet_choose_title] = [c.facet_choose_item]

            context = {'model': model, 'session': model.Session,
                       'user': c.user or c.author, 'for_view': True}

            if not asbool(config.get('ckan.search.show_all_types', 'False')):
                fq += ' +dataset_type:dataset'

            facets = OrderedDict()

            default_facet_titles = {
                    'organization': _('Organizations'),
                    'groups': _('Groups'),
                    'tags': _('Tags'),
                    'res_format': _('Formats'),
                    'license_id': _('License'),
                    }

            for facet in g.facets:
                if facet in default_facet_titles:
                    facets[facet] = default_facet_titles[facet]
                else:
                    facets[facet] = facet

            # Facet titles
            for plugin in p.PluginImplementations(p.IFacets):
                facets = plugin.dataset_facets(facets, package_type)

            c.facet_titles = facets

            data_dict = {
                'q': q,
                'fq': fq.strip(),
                'facet.field': facets.keys(),
                'rows': limit,
                'start': (page - 1) * limit,
                'sort': sort_by,
                'extras': search_extras
            }

            query = get_action('package_search')(context, data_dict)
            c.sort_by_selected = query['sort']

            c.page = h.Page(
                collection=query['results'],
                page=page,
                url=pager_url,
                item_count=query['count'],
                items_per_page=limit
            )
            c.facets = query['facets']
            c.search_facets = query['search_facets']
            c.page.items = query['results']
        except SearchError, se:
            log.error('Dataset search error: %r', se.args)
            c.query_error = True
            c.facets = {}
            c.search_facets = {}
            c.page = h.Page(collection=[])
        c.search_facets_limits = {}
        for facet in c.search_facets.keys():
            limit = 0
            c.search_facets_limits[facet] = limit

        maintain.deprecate_context_item(
          'facets',
          'Use `c.search_facets` instead.')

        return render('kata/browse.html')

    def read(self, id):
        _or_ = sqlalchemy.or_
        query = model.Session.query(model.Package).filter(_or_(model.Package.name == id, model.Package.id == id)).first()
        if query and query.state == 'deleted':
            c.org = model.Session.query(model.Group).filter(model.Group.id == query.owner_org).first()
            c.title_json = query.title
            return render('kata/tombstone.html')

        return super(KataPackageController, self).read(id)


class KataInfoController(BaseController):
    '''
    KataInfoController provides info pages, which
    are non-dynamic and visible for all
    '''

    def render_data_model(self):
        '''
        Provides the data-model as a separate page
        '''

        return render('kata/data-model.html')


class KataHomeController(HomeController):
    '''
    KataHomeController rewrites features of CKAN's home controller.

    '''
    def index(self):
        '''
        Simplified index function compared to CKAN's original one.

        :return: render home/index.html
        '''

        try:
            # package search
            context = {'model': model, 'session': model.Session,
                       'user': c.user or c.author, 'schema': kata_schemas.package_search_schema()}
            data_dict = {
                'q': '*:*',
                'facet.field': g.facets,
                'facet.limit': -1,
                'rows': 0,
                'start': 0,
                'sort': 'title_string desc',
                'fq': 'capacity:"public" +dataset_type:dataset'
            }
            query = logic.get_action('package_search')(
                context, data_dict)
            c.package_count = query['count']

            c.facets = query['facets']
            maintain.deprecate_context_item(
                'facets',
                'Use `c.search_facets` instead.')

            c.search_facets = query['search_facets']

            c.num_tags = len(c.facets.get('tags'))
            c.num_discipline = len(c.facets.get('extras_discipline'))

        except search.SearchError:
            c.package_count = 0
            c.groups = []
            c.num_tags = 0
            c.num_discipline = 0

        return render("home/index.html", cache_force=True)
