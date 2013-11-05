# pylint: disable=unused-argument

"""
Functions to convert dataset form fields from or to db fields.
"""

from pylons import h

import re
import utils
import logging
from pylons.i18n import _

from ckan.logic.action.create import related_create
from ckan.model import Related, Session, Group, repo
from ckan.lib.navl.validators import not_empty
from ckan.model.authz import setup_default_user_roles

log = logging.getLogger('ckanext.kata.converters')


def pid_from_extras(key, data, errors, context):
    '''
    Get versionPID from extras or generate a new one.
    '''
    for k in data.keys():
        if k[0] == 'extras' and k[-1] == 'key' and data[k] == 'versionPID':
            data[('versionPID',)] = data[(k[0], k[1], 'value')]

            for _remove in data.keys():
                if _remove[0] == 'extras' and _remove[1] == k[1]:
                    del data[_remove]

    if not ('versionPID',) in data:
        data[('versionPID',)] = utils.generate_pid()


def org_auth_to_extras(key, data, errors, context):
    '''
    Convert author and organization to extras
    '''
    extras = data.get(('extras',), [])
    if not extras:
        data[('extras',)] = extras
    if len(data[key]) > 0:
        if key[0] == 'author':
            if not ('organization', key[1], key[2]) in data:
                errors[key].append(_('This author is without organization!'))
        if key[0] == 'organization':
            if not ('author', key[1], key[2]) in data:
                errors[key].append(_('This organization is without author!'))
        extras.append({'key': "%s_%s" % (key[0], key[1]),
                  'value': data[key]})


def org_auth_from_extras(key, data, errors, context):
    '''
    Convert (author, organization) pairs from package.extra to 'orgauths' dict
    '''
    if not ('orgauths',) in data:
        data[('orgauths',)] = []
    auths = []
    orgs = []
    orgauths = data[('orgauths',)]
    for k in data.keys():
        if k[0] == 'extras' and k[-1] == 'key':
            if 'author_' in data[k]:
                val = data[(k[0], k[1], 'value')]
                auth = {}
                auth['key'] = data[k]
                auth['value'] = val
                if not {'key': data[k], 'value': val} in auths:
                    auths.append(auth)

            if 'organization_' in data[k]:
                org = {}
                val = data[(k[0], k[1], 'value')]
                org['key'] = data[k]
                org['value'] = val
                if not {'key': data[k], 'value': val} in orgs:
                    orgs.append(org)

    orgs = sorted(orgs, key=lambda ke: int(ke['key'][-1]))
    auths = sorted(auths, key=lambda ke: int(ke['key'][-1]))
    zipped = zip(orgs, auths)
    if zipped:
        for org, auth in zipped:
            if not (auth, org) in orgauths:
                orgauths.append((auth, org))
    else:
        for org in orgs:
            if not ("", org) in orgauths:
                orgauths.append(("", org))
        for auth in auths:
            if not (auth, "") in orgauths:
                orgauths.append((auth, ""))


def ltitle_to_extras(key, data, errors, context):
    """
    Convert title & language pair from dataset form to db format and validate.
    Title & language pairs will be stored in package_extra.
    """

    extras = data.get(('extras',), [])
    langs = []

    if not extras:
        data[('extras',)] = extras

    if len(data[key]) > 0:
        # Get title's language from data dictionary. key[0] == 'title'.
        lval = data[(key[0], key[1], 'lang')]

        if not lval in langs:
            langs.append(lval)
        else:
            if not _("Duplicate language found.") in errors[key]:
                errors[key].append(_("Duplicate language found."))

        extras.append({'key': "title_%s" % key[1],
                      'value': data[key]})
        extras.append({'key': 'lang_title_%s' % key[1],
                       'value': lval
                       })

    if key[1] == 0 and len(data[key]) == 0 and not (key[0], key[1] + 1, 'value') in data:
        errors[key].append(_('Add at least one non-empty title!'))


def ltitle_from_extras(key, data, errors, context):
    """
    Convert title & language pair from db format to dataset form format.
    """
    if not ('langtitles',) in data:
        data[('langtitles',)] = []
    auths = []
    orgs = []
    orgauths = data[('langtitles',)]
    for k in data.keys():
        if 'extras' in k and 'key' in k:
            if re.search('^(title_|ltitle)\d+$', data[k]):
                val = data[(k[0], k[1], 'value')]
                auth = {'key': data[k], 'value': val}
                if auth not in auths:
                    auths.append(auth)

            if re.search('^(lsel|lang_title_)\d+$', data[k]):
                val = data[(k[0], k[1], 'value')]
                org = {'key': data[k], 'value': val}
                if org not in orgs:
                    orgs.append(org)
    orgs = sorted(orgs, key=lambda ke: int(ke['key'].rsplit('_', 1)[1]))
    auths = sorted(auths, key=lambda ke: int(ke['key'].rsplit('_', 1)[1]))
    for org, auth in zip(orgs, auths):
        if not (auth, org) in orgauths:
            orgauths.append((auth, org))


def event_to_extras(key, data, errors, context):
    '''
    Parses separate 'ev*' parameters from 'data' data_dict to 'extra' field
    in that same 'data'.
    @param key: key from schema, 'evtype', 'evdescr' etc.
    @param data: whole data_dict passed for modification
    '''
    #log.debug("event_to_extras(): key: %s : %s", str(key), str(data[key]))

    extras = data.get(('extras',), [])
    if not extras:
        data[('extras',)] = extras
    if (key[2] == 'value' and len(data[key]) > 0 and type(data[key]) == unicode):
        extras.append({'key': "%s_%d" % (key[0], key[1]),
                       'value': data[key]
                      })

def event_from_extras(evkey, data, errors, context):
    if not ('events',) in data:
        data[('events',)] = []
    types = []
    whos = []
    whens = []
    descrs = []
    events = data[('events',)]

    #evvalues = []

    log.debug("event_FROM_extras(key, ...): evkey: %s" % str(evkey))

    # TODO: rewrite to extract each key:value with its key's validator
    #for k in data.keys():
    #    if k[0] == 'extras' and k[-1] == 'key':
    #        if evkey[0] in data[k]:
    #            # evindex = int(data[k].split('_')[-1])
    #            val = data[(k[0], k[1], 'value')]
    #            if not {'key': data[k], 'value': val} in evvalues:
    #            evvalues.append({'key': data[k], 'value': val})

    #evvalues = sorted(evvalues, key=lambda evdict: int(evdict['key'].split('_')[-1]))

    for k in data.keys():
        if k[0] == 'extras' and k[-1] == 'key':
            if 'evtype' in data[k]:
                val = data[(k[0], k[1], 'value')]
                type = {'key': data[k]}
                type['value'] = val
                if not {'key': data[k], 'value': val} in types:
                    types.append(type)
            if 'evwho' in data[k]:
                val = data[(k[0], k[1], 'value')]
                who = {'key': data[k]}
                who['value'] = val
                if not {'key': data[k], 'value': val} in whos:
                    whos.append(who)
            if 'evwhen' in data[k]:
                val = data[(k[0], k[1], 'value')]
                when = {'key': data[k]}
                when['value'] = val
                if not {'key': data[k], 'value': val} in whens:
                    whens.append(when)
            if 'evdescr' in data[k]:
                val = data[(k[0], k[1], 'value')]
                descr = {'key': data[k]}
                descr['value'] = val
                if not {'key': data[k], 'value': val} in descrs:
                    descrs.append(descr)

    types = sorted(types, key=lambda ke: int(ke['key'].split('_')[-1]))
    whos = sorted(whos, key=lambda ke: int(ke['key'].split('_')[-1]))
    whens = sorted(whens, key=lambda ke: int(ke['key'].split('_')[-1]))
    descrs = sorted(descrs, key=lambda ke: int(ke['key'].split('_')[-1]))

    for etype, ewho, ewhen, edescr in zip(types, whos, whens, descrs):
        if not (etype, ewho, ewhen, edescr) in events:
            events.append((etype, ewho, ewhen, edescr))


def export_as_related(key, data, errors, context):
    if 'id' in data[('__extras',)]:
        for value in data[key].split(';'):
            if value != '':
                if len(Session.query(Related).filter(Related.title == value).all()) == 0:
                    data_dict = {'title': value,
                                 'type': _("Paper"),
                                 'dataset_id': data[('__extras',)]['id']}
                    related_create(context, data_dict)


def add_to_group(key, data, errors, context):
    '''
    Add a new group if it doesn't yet exist.
    '''
    val = data.get(key)
    if val:
        repo.new_revision()
        grp = Group.get(val)
        # UI code needs group created if it does not match. Hence do so.
        if not grp:
            grp = Group(name=val, description=val, title=val)
            setup_default_user_roles(grp)
            grp.save()
        repo.commit()


def remove_disabled_languages(key, data, errors, context):
    '''
    If langdis == 'True', remove all languages.

    Expecting language codes in data['key'].
    '''
    langdis = data.get(('langdis',))

    langs = data.get(key).split(',')

    if langdis == 'False':
        # Language enabled

        if langs == [u'']:
            errors[key].append(_('No language given.'))
    else:
        # Language disabled

        # Display flash message if user is loading a page.
        if 'session' in globals():
            h.flash_notice(_("Language is disabled, removing languages: '%s'" % data[key]))

        # Remove languages.
        del data[key]
        data[key] = u''


def checkbox_to_boolean(key, data, errors, context):
    '''
    Convert HTML checkbox's value ('on' / null) to boolean string
    '''
    value = data.get(key, None)

    if value not in [u'True', u'False']:
        if value == u'on':
            data[key] = u'True'
        else:
            data[key] = u'False'



