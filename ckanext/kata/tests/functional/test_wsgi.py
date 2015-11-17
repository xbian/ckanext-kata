# coding: utf-8
'''
Test Kata's web user interface with Pylons WSGI application.
'''
import copy
import json

import lxml.etree
from ckanext.harvest import model as harvest_model
from lxml import etree

import ckan.model as model
import ckanext.kata.model as kata_model
from ckan.logic import get_action
from ckan.tests.legacy import url_for
from ckanext.kata import settings, utils
from ckanext.kata.tests.functional import KataWsgiTestCase
from ckanext.kata.tests.test_fixtures.unflattened import TEST_DATADICT
from ckanext.kata.controllers import ContactController


# TODO: A WSGI test to parse pages with lxml to make sure there are no tag errors.

class TestPages(KataWsgiTestCase):
    """
    Simple tests to see that pages render properly.
    """

    def test_group_page(self):
        """
        Test that help page is found and rendered.
        """
        offset = url_for('/group')
        res = self.app.get(offset)
        assert res.status == 200, 'Wrong HTTP status code (expecting 200)'

    # def test_harvest_page(self):
    #     # TODO: This seems to always get 404 from app.get, this should be solved somehow if possible.
    #     # Where is "/harvest" added to routes anyway?
    #
    #     res = self.app.get('/harvest', extra_environ={})
    #     assert res.status == 200, 'Wrong HTTP status code (expecting 200)'

    def test_dataset_page(self):
        offset = url_for('/dataset')
        res = self.app.get(offset)
        assert res.status == 200, 'Wrong HTTP status code (expecting 200)'

    def test_urnexport_page(self):
        offset = url_for('/urnexport')
        res = self.app.get(offset)
        assert res.status == 200, 'Wrong HTTP status code (expecting 200)'


class TestResources(KataWsgiTestCase):
    """
    Test that resources are handled properly in WUI.
    """

    # def test_data_and_resources_not_rendered(self):
    #     """
    #     A package with no resources should not render Data and Resources section
    #     """
    #     offset = url_for(controller='package', action='read', id=u'warandpeace')
    #     res = self.app.get(offset)
    #     assert '<section id="dataset-resources"' not in res, 'A package with no resources should not render Data and Resources section'
    #
    # def test_data_and_resources_rendered(self):
    #     """
    #     A package with resources should render Data and Resources section
    #     """
    #     offset = url_for(controller='package', action='read', id=u'annakarenina')
    #     res = self.app.get(offset)
    #     assert '<section id="dataset-resources"' in res, 'A package with resources should render Data and Resources section'

    def test_resource_read_redirect(self):
        """
        resource_read should redirect to dataset page.
        """
        res_id = None

        pkg = model.Package.get(u'annakarenina')
        for resource in pkg.resources:
            if 'Full text.' in resource.description:
                revision = model.repo.new_revision()
                resource.resource_type = settings.RESOURCE_TYPE_DATASET
                model.Session.commit()
                res_id = resource.id

        offset = '/en' + url_for(controller='package', action='resource_read',
                                 id=u'annakarenina', resource_id=res_id)

        extra_environ = {'REMOTE_USER': 'tester'}
        result = self.app.get(offset, extra_environ=extra_environ)

        # Redirect should redirect to dataset page
        result = result.follow()

        assert result.body.count('Full text.') == 1

        # resources_obj = etree.lxml.etree.fromstring(result.body).xpath("//u:identifier", namespaces=self.namespaces)
        # with open('/var/www/foo.txt', mode='wt') as f:
        #     f.write(result.body)
        # resources_obj = etree.fromstring(result.body).xpath("//div[div[text()='Files']]", namespaces=self.namespaces)
        # res_table = resources_obj.xpath("/div/table/tbody")

        # import pprint
        # pprint.pprint(dir(res_table))

    #         assert 'Full text.' in result.body

    # regex = re.compile(r'<a.*href.*>.*Edit\w*</a>')
    # assert not regex.search(result.body), "%r" % result.body

    # assert 'Edit Profile' in result.body    # Sanity check


class TestRdfExport(KataWsgiTestCase):
    '''
    Test RDF export.
    '''

    def test_has_rdf_tags(self):
        offset = url_for(controller='package', action='read', id=u'warandpeace') + '.rdf'
        res = self.app.get(offset)

        assert "<rdf" in res
        assert "</rdf" in res


class TestContactForm(KataWsgiTestCase):
    '''
    Test dataset contact form
    '''

    def test_contact_controller_no_user(self):
        """
        Test that we get a redirect when there is no user
        """
        offset = url_for("/contact/warandpeace")
        res = self.app.get(offset)
        assert res.status == 200, 'Everyone is allowed to contact'

    def test_contact_controller_user_logged_in(self):
        '''
        Test that we get the contact form when user is logged in

        Note: Form should probably be only visible if the dataset can be requested via the form?
        '''

        extra_environ = {'REMOTE_USER': 'tester'}

        offset = url_for("/contact/warandpeace")
        res = self.app.post(offset, extra_environ=extra_environ)

        print offset
        print res

        assert all(piece in res.body for piece in ['<form', '/contact/send/', '</form>']), 'Contact form not rendered'

    def test_contact(self):

        data = copy.deepcopy(TEST_DATADICT)
        data['private'] = False
        data['contact'][0]['email'] = 'kata.selenium@gmail.com'
        data['id'] = 'test-contact'
        data['name'] = 'test-contact'

        model.User(name="test_sysadmin", sysadmin=True).save()

        organisation = get_action('organization_create')({'user': 'test_sysadmin'}, {'name': 'test-organization',
                                                                                     'title': "Test organization"})
        data['owner_org'] = organisation.get('name')
        get_action('package_create')({'user': 'test_sysadmin'}, data)

        offset = url_for("/contact/send/test-contact")
        res = self.app.post(offset, params={'recipient': utils.get_package_contacts(data.get('name'))[0].get('id')})
        assert res.status == 302

        offset = url_for("/dataset/test-contact")
        res = self.app.post(offset)
        assert 'Message not sent' in res

        import base64
        import time

        cc = ContactController()
        _time = base64.b64encode(cc.crypto.encrypt(cc._pad(str(int(time.time())))))

        offset = url_for("/contact/send/test-contact")
        params = {
            'recipient': utils.get_package_contacts(data.get('name'))[0].get('id'),
            'check_this_out': _time,
            'accept_logging': 'True'
        }
        self.app.post(offset, params=params, status=302)

        offset = url_for("/dataset/test-contact")
        res = self.app.post(offset)

        assert 'spam bot' in res

        _time = base64.b64encode(cc.crypto.encrypt(cc._pad(str(int(time.time())-21))))
        offset = url_for("/contact/send/test-contact")
        params = {
            'recipient': utils.get_package_contacts(data.get('name'))[0].get('id'),
            'check_this_out': _time,
            'accept_logging': 'True'
        }
        self.app.post(offset, params=params, status=302)
        offset = url_for("/dataset/test-contact")
        res = self.app.post(offset)

        assert 'Message not sent' in res

class TestDatasetEditorManagement(KataWsgiTestCase):
    '''
    Test the dataset editor management page's visibility
    '''

    def test_dataset_management_page_not_renders(self):
        '''
        Test that non-editor can not see the dataset administration page
        '''
        offset = url_for(controller='ckanext.kata.controllers:KataPackageController', action='dataset_editor_manage',
                         name=u'warandpeace')

        extra_environ = {'REMOTE_USER': 'tester'}
        res = self.app.get(offset, extra_environ=extra_environ)
        assert res.status == 302, 'Expecting a redirect when user has no edit rights'

    def test_dataset_management_page_renders(self):
        '''
        Test that the dataset management page renders
        '''
        offset = url_for(controller='ckanext.kata.controllers:KataPackageController', action='dataset_editor_manage',
                         name=u'annakarenina')

        extra_environ = {'REMOTE_USER': 'testsysadmin'}
        res = self.app.get(offset, extra_environ=extra_environ)
        assert 'Add a user for role' in res, \
            u'User should see the dataset management page'


class TestAuthorisation(KataWsgiTestCase):
    '''
    Test Kata authorisation functions
    '''

    def test_edit_not_available(self):
        '''
        Test that edit page is not available for random user
        '''
        offset = url_for("/dataset/edit/annakarenina")

        extra_environ = {'REMOTE_USER': 'russianfan'}
        res = self.app.get(offset, extra_environ=extra_environ, status=401)

    def test_delete_not_available(self):
        '''
        Test that deletion of a dataset is not available
        for an unauthorised user
        '''
        offset = url_for("/dataset/delete/annakarenina")
        extra_environ = {'REMOTE_USER': 'russianfan'}
        res = self.app.get(offset, extra_environ=extra_environ, status=401)

    def test_delete_available(self):
        '''
        Test that delete button exists for package editor
        '''
        offset = url_for(controller='package', action='edit', id=u'annakarenina')
        pkg_id = u'annakarenina'
        user_id = u'tester'
        user = model.User.get(user_id)
        pkg = model.Package.get(pkg_id)
        model.meta.Session.commit()
        model.authz.add_user_to_role(user, 'editor', pkg)

        extra_environ = {'REMOTE_USER': 'tester'}
        res = self.app.get(offset, extra_environ=extra_environ)

        assert 'Are you sure you want to delete this dataset?' in res, \
            'Dataset owner should have the delete button available'


class TestURNExport(KataWsgiTestCase):
    '''
    Test urn export
    '''

    namespaces = {'u': 'urn:nbn:se:uu:ub:epc-schema:rs-location-mapping'}

    @classmethod
    def setup_class(cls):
        kata_model.setup()
        harvest_model.setup()

        model.User(name="test_sysadmin", sysadmin=True).save()

    @classmethod
    def teardown_class(cls):
        model.repo.rebuild_db()

    def test_urnexport(self):
        from ckanext.kata import controllers

        # Switch to use uncached urnexport:
        controllers.MetadataController.urnexport = controllers.MetadataController._urnexport

        offset = url_for('/urnexport')
        res = self.app.get(offset)

        # No datasets to export
        self.assertEquals(len(lxml.etree.fromstring(res.body).xpath("//u:identifier", namespaces=self.namespaces)), 0)
        assert res.body.count('<identifier>') == 0

        organization = get_action('organization_create')({'user': 'test_sysadmin'},
                                                         {'name': 'test-organization', 'title': "Test organization"})

        for count, private, delete in (1, False, False), (1, True, False), (2, False, False), (2, False, True), (
        3, False, False):
            data = copy.deepcopy(TEST_DATADICT)
            data['owner_org'] = organization['name']
            data['private'] = private

            package = get_action('package_create')({'user': 'test_sysadmin'}, data)
            if delete:
                get_action('package_delete')({'user': 'test_sysadmin'}, {'id': package['id']})

            res = self.app.get(offset)

            tree = lxml.etree.fromstring(res.body)
            self.assertEquals(len(tree.xpath("//u:identifier", namespaces=self.namespaces)), count)

            try:
                etree.XML(res.body)  # Validate that result is XML
            except etree.LxmlError:
                self.fail('Unexpected XML parsing error')


class TestKataApi(KataWsgiTestCase):
    '''
    Test custom HTTP API.
    '''

    def test_funder_autocomplete(self):
        result = self.app.get(
            url_for(controller="ckanext.kata.controllers:KATAApiController", action='funder_autocomplete',
                    incomplete=u'eu'))
        results = json.loads(unicode(result.body))['ResultSet']['Result']
        self.assertTrue({"Name": "EU muu rahoitus - EU other funding"} in results)


class TestMetadataSupplements(KataWsgiTestCase):
    '''
    Test metadata supplements.
    '''

    def test_01_button(self):
        '''
        Test that button renders
        '''
        organization = get_action('organization_create')({'user': 'testsysadmin'},
                                                         {'name': 'unseen-academy',
                                                          'title': "Unseen Academy"})

        data = copy.deepcopy(TEST_DATADICT)
        data['owner_org'] = organization['name']
        data['name'] = 'metadata-supplement-testdataset'

        package = get_action('package_create')({'user': 'testsysadmin'}, data)
        offset = url_for(controller='package', action='read', id=u'metadata-supplement-testdataset')
        extra_environ = {'REMOTE_USER': 'testsysadmin'}
        res = self.app.get(offset, extra_environ=extra_environ)
        assert '/dataset/new_resource/' in res

    def test_02_formpage(self):
        '''
        Test that metadata supplement form renders
        '''
        package = get_action('package_show')({'user': 'testsysadmin'},
                                             {'id': 'metadata-supplement-testdataset'})
        offset = url_for('/en/dataset/new_resource/{0}'.format(package['name']))
        extra_environ = {'REMOTE_USER': 'testsysadmin'}
        res = self.app.get(offset, extra_environ=extra_environ)
        assert 'resource-upload-field' in res

        get_action('package_delete')({'user': 'testsysadmin'}, package)


class TestKataOrganizationController(KataWsgiTestCase):
    '''Test organization controller'''

    def test_organization_hiding_pagination(self):
        model.User(name="test_sysadmin", sysadmin=True).save()

        orgs = []

        for x in range(50):  # Create 50 organizations
            org_id = 'org_{x}'.format(x=str(x))
            org_title = 'Organisation {x}'.format(x=str(x))
            orgs.append(get_action('organization_create')({'user': 'test_sysadmin'},
                                                          {'name': org_id, 'title': org_title}))

        for org in orgs[::2]:  # Create 25 datasets to distinct organizations
            data = copy.deepcopy(TEST_DATADICT)
            data['owner_org'] = org['name']
            data['name'] = org['id']
            get_action('package_create')({'user': 'test_sysadmin'}, data)

        res = self.app.get(url_for("/organization"), status=200)

        # Page 1:

        assert res.body.count('>0 Datasets<') == 0
        assert res.body.count('>1 Dataset<') == 21

        assert res.body.count('25 organizations found')

        # Page 2:

        res = self.app.get(url_for("/organization?sort=&q=&page=2"), status=200)

        assert res.body.count('>0 Datasets<') == 0
        assert res.body.count('>1 Dataset<') == 4

        assert res.body.count('25 organizations found')

