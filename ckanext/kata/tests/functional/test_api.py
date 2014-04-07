# coding: utf-8
#
# pylint: disable=no-self-use, missing-docstring, too-many-public-methods, star-args

"""
Functional tests for Kata that use CKAN API.
"""

import copy
import logging
import unittest

import paste.fixture
from pylons import config
import testfixtures

from ckan import model
from ckan.config.middleware import make_app
from ckan.lib.create_test_data import CreateTestData
from ckan.tests import call_action_api

import ckanext.kata.model as kata_model
import ckanext.kata.settings as settings
from ckanext.kata.tests.functional import KataApiTestCase


TEST_RESOURCE = {'url': u'http://www.helsinki.fi',
                 'algorithm': u'SHA',
                 'hash': u'somehash',
                 'mimetype': u'application/csv',
                 'resource_type': 'file'}

TEST_DATADICT = {'access_application_new_form': u'False',
                 'agent': [{'role': u'author',
                            'name': u'T. Tekijä',
                            'organisation': u'O-Org',},
                           {'role': u'contributor',
                            'name': u'R. Runoilija',
                            'id': u'lhywrt8y08536tq3yq',
                            'organisation': u'Y-Yritys',
                            'URL': u'http://www.yyritys.kata.fi'},
                           {'role': u'funder',
                            'name': u'R. Ahanen',
                            'organisation': u'CSC Oy',
                            'URL': u'www.csc.fi',
                            'funding-id': u'12345-ABCDE-$$$',},
                           {'role': u'owner',
                            'organisation': u'CSC Oy',
                            'URL': u'www.csc.fi',},
                           {'role': u'distributor',
                            'organisation': u'CSC Oy',
                            'URL': u'www.csc.fi',},
                           {'role': u'contributor',
                            'name': u'V. Ajavainen',
                            'organisation': u'CSC Oy',
                            }],

                 'algorithm': u'MD5',
                 'availability': u'direct_download',
                 'checksum': u'f60e586509d99944e2d62f31979a802f',
                 'contact_URL': u'http://www.tdata.fi',
                 'contact_phone': u'05549583',
                 'direct_download_URL': u'http://www.tdata.fi/kata',
                 'discipline': u'Tietojenkäsittely ja informaatiotieteet',
                 'evdescr': [{'value': u'Kerätty dataa'},
                             {'value': u'Alustava julkaistu'},
                             {'value': u'Lisätty dataa'}],
                 'evtype': [{'value': u'creation'},
                            {'value': u'published'},
                            {'value': u'modified'}],
                 'evwhen': [{'value': u'2000-01-01'},
                            {'value': u'2010-04-15'},
                            {'value': u'2013-11-18'}],
                 'evwho': [{'value': u'T. Tekijä'},
                           {'value': u'J. Julkaisija'},
                           {'value': u'M. Muokkaaja'}],
                 'geographic_coverage': u'Keilaniemi (populated place),Espoo (city)',
                 'langdis': 'False',
                 'langtitle': [{'lang': u'fin', 'value': u'Test Data'},
                               {'lang': u'abk', 'value': u'Title 2'},
                               {'lang': u'swe', 'value': u'Title 3'}],
                 'language': u'eng, fin, swe',
                 'license_id': u'notspecified',
                 'maintainer': u'J. Jakelija',
                 'maintainer_email': u'j.jakelija@csc.fi',
                 'mimetype': u'application/csv',
                 'name': u'',
                 'notes': u'Vapaamuotoinen kuvaus aineistosta.',
                 # 'orgauth': [{'org': u'CSC Oy', 'value': u'T. Tekijä'},
                 #             {'org': u'Helsingin Yliopisto', 'value': u'T. Tutkija'},
                 #             {'org': u'Org 3', 'value': u'K. Kolmas'}],
                 # 'owner': u'Ossi Omistaja',
                 # 'pids': {
                 #     u'http://helda.helsinki.fi/oai/request': {
                 #         'data': [u'some_data_pid', u'another_data_pid'],
                 #         'metadata': [u'metadata_pid', u'another_metadata_pid', u'third_metadata_pid'],
                 #         'version': [u'version_pid', u'another_version_pid'],
                 #     },
                 #     'kata': {
                 #         'version': [u'kata_version_pid'],
                 #     },
                 # },
                 'pids': [
                     {
                         'provider': u'http://helda.helsinki.fi/oai/request',
                         'id': u'some_data_pid',
                         'type': u'data',
                     },
                     {
                         'provider': u'kata',
                         'id': u'kata_data_pid',
                         'type': u'data',
                     },
                     {
                         'provider': u'kata',
                         'id': u'kata_metadata_PID',
                         'type': u'metadata',
                     },
                     {
                         'provider': u'kata',
                         'id': u'kata_version_PID',
                         'type': u'version',
                     },
                 ],
                 # 'projdis': 'False',
                 # 'project_funder': u'NSA',
                 # 'project_funding': u'1234-rahoituspäätösnumero',
                 # 'project_homepage': u'http://www.csc.fi',
                 # 'project_name': u'Tutkimusprojekti',
                 'tag_string': u'Python,ohjelmoitunut solukuolema,programming',
                 'temporal_coverage_begin': u'2003-07-10T06:36:27Z',
                 'temporal_coverage_end': u'2010-04-15T03:24:47Z',
                 'title': u'',
                 'type': u'dataset',
                 'version': u'2013-11-18T12:25:53Z',
                 'xpaths': {
                     'xpath/path1': u'xpath_value',
                     'xpath/path2': u'xpath_value2',
                 },
}


class TestCreateDatasetAndResources(KataApiTestCase):
    """Tests for creating datasets and resources through API."""

    def test_create_dataset(self):
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert output
        assert output['id'].startswith('urn:nbn:fi:csc-kata')

    def test_create_dataset_sysadmin(self):
        output = call_action_api(self.app, 'package_create', apikey=self.sysadmin_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert output
        assert output['id'].startswith('urn:nbn:fi:csc-kata')

    def test_create_dataset_and_resources(self):
        '''
        Add a dataset and 20 resources and read dataset through API
        '''
        print 'Create dataset'
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        new_res = copy.deepcopy(TEST_RESOURCE)
        new_res['package_id'] = output['id']

        for res_num in range(20):
            print 'Adding resource %r' % (res_num + 1)

            output = call_action_api(self.app, 'resource_create', apikey=self.normal_user.apikey,
                                     status=200, **new_res)
            if '__type' in output:
                assert output['__type'] != 'Validation Error'
            assert output

        print 'Read dataset'
        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=new_res['package_id'])
        assert 'id' in output

        # Check that some metadata value is correct.
        assert output['checksum'] == TEST_DATADICT['checksum']

    def test_create_update_delete_dataset(self):
        '''
        Add, modify and delete a dataset through API
        '''
        print 'Create dataset'
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        data_dict = copy.deepcopy(TEST_DATADICT)
        data_dict['id'] = output['id']

        print 'Update dataset'
        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey, status=200, **data_dict)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert output

        print 'Update dataset'
        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey, status=200, **data_dict)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert output

        print 'Delete dataset'
        output = call_action_api(self.app, 'package_delete', apikey=self.normal_user.apikey,
                                 status=200, id=data_dict['id'])

    def test_create_dataset_fails(self):
        data = copy.deepcopy(TEST_DATADICT)

        # Make sure we will get a validation error
        data.pop('langtitle')
        data.pop('language')
        data.pop('availability')

        # Hide validation error message which cannot be silenced with nosetest parameters. Has to be done here.
        logg = logging.getLogger('ckan.controllers.api')
        logg.disabled = True

        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=409, **data)

        logg.disabled = False

        assert '__type' in output
        assert output['__type'] == 'Validation Error'

    def test_create_and_delete_resources(self):
        '''
        Add a dataset and add and delete a resource through API
        '''
        print 'Create dataset'
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        print 'Add resource #1'
        new_res = copy.deepcopy(TEST_RESOURCE)
        new_res['package_id'] = output['id']

        output = call_action_api(self.app, 'resource_create', apikey=self.normal_user.apikey,
                                 status=200, **new_res)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert output

        res_id = output['id']

        print 'Delete resource #1'
        # For some reason this is forbidden for the user that created the resource
        output = call_action_api(self.app, 'resource_delete', apikey=self.sysadmin_user.apikey,
                                 status=200, id=res_id)
        if output is not None and '__type' in output:
            assert output['__type'] != 'Validation Error'
            
    def test_create_edit(self):
        '''
        Test and edit dataset via API. Check that immutables stay as they are.
        '''
        print 'Create dataset'
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        
        data_dict = copy.deepcopy(TEST_DATADICT)
        
        orig_id = output['id']
        data_dict['id'] = orig_id
        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey, status=200, **data_dict)
        assert output['id'] == orig_id
        
        data_dict['name'] = 'new-name-123456'

        print 'Update dataset'
        
        log = logging.getLogger('ckan.controllers.api')     # pylint: disable=invalid-name
        log.disabled = True
        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey, status=409, **data_dict)
        log.disabled = False
        
        assert output
        assert '__type' in output
        assert output['__type'] == 'Validation Error'
        

class TestDataReading(KataApiTestCase):
    '''
    Tests for checking that values match between original data_dict and package_show output.
    '''

    def _compare_datadicts(self, output):
        '''
        Compare a CKAN generated datadict to TEST_DATADICT
        '''

        data_dict = copy.deepcopy(TEST_DATADICT)

        # name (data pid) and title are generated so they shouldn't match
        data_dict.pop('name', None)
        data_dict.pop('title', None)

        # Events come back in different format, so skip checking them for now
        # TODO: check events when event format is fixed
        data_dict.pop('evdescr', None)
        data_dict.pop('evtype', None)
        data_dict.pop('evwho', None)
        data_dict.pop('evwhen', None)

        # TODO: Removed because: xpath-json converter not working
        data_dict.pop('xpaths', None)
        output.pop('xpaths', None)

        # Removed because more values returned from db than needed, for now.
        # Tässä joudutaan poistelemaan paljon sillä titlen, resourcen ym.
        # käsittelyssä kannasta palautuvat arvot (dictit) ovat erilaisia kuin
        # sinne tallennettavat arvot. Lisäksi action palauttaa paljon automaat-
        # sesti muodostettuja arvoja kuten 'relationships_as_object'.
        output.pop('events', None)
        output.pop('groups', None)
        output.pop('id', None)
        output.pop('isopen', None)
        output.pop('license_title', None)
        output.pop('metadata_created', None)
        output.pop('metadata_modified', None)
        output.pop('name', None)
        output.pop('num_resources', None)
        output.pop('num_tags', None)
        output.pop('owner_org', None)
        output.pop('private', None)
        output.pop('relationships_as_object', None)
        output.pop('relationships_as_subject', None)
        output.pop('resources', None)
        output.pop('revision_id', None)
        output.pop('revision_timestamp', None)
        output.pop('state', None)
        output.pop('tags', None)
        output.pop('title', None)
        output.pop('tracking_summary', None)
        output.pop('url', None)

        testfixtures.compare(output, data_dict)

        return True

    def test_create_and_read_dataset(self):
        '''
        Create and read a dataset through API and check that values are correct
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=output['id'])

        assert self._compare_datadicts(output)

    def test_create_and_read_dataset_2(self):
        '''
        Create and read a dataset through API and check that values are correct.
        Read as a different user than dataset creator.
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.sysadmin_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=output['id'])

        # Handle hidden fields
        output.pop('project_funding', None)
        output['maintainer_email'] = TEST_DATADICT['maintainer_email']

        assert self._compare_datadicts(output)

    def test_create_update_and_read_dataset(self):
        '''
        Create, update and read a dataset through API and check that values are correct
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        data_dict = copy.deepcopy(TEST_DATADICT)
        data_dict['id'] = output['id']

        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey,
                                 status=200, **data_dict)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=output['id'])

        assert self._compare_datadicts(output)
        
    def test_secured_fields(self):
        '''
        Test that anonymous user can not read protected data
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        if '__type' in output:
            assert output['__type'] != 'Validation Error'
        assert 'id' in output
        
        output = call_action_api(self.app, 'package_show',
                                 status=200, id=output['id'])
        assert output
        assert output['maintainer_email'] == u'Not authorized to see this information'
        assert output['project_funding'] == u'Not authorized to see this information'

    def test_availability_changing(self):
        '''
        Test that changing availability removes unused availability URL's and dataset resource URL
        '''

        ACCESS_URL = 'http://www.csc.fi/english/'

        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        assert 'id' in output

        data_dict = copy.deepcopy(TEST_DATADICT)
        data_dict['id'] = output['id']
        data_dict['availability'] = 'access_application'
        data_dict['access_application_URL'] = ACCESS_URL

        # UPDATE AVAILABILITY

        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey,
                                 status=200, **data_dict)
        assert 'id' in output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=output['id'])

        # import pprint
        # pprint.pprint(output)

        assert output.get('access_application_URL') == ACCESS_URL
        assert output.get('direct_download_URL') == settings.DATASET_URL_UNKNOWN, output['direct_download_URL']

        assert 'algorithm' in output
        assert 'checksum' in output
        assert 'mimetype' in output

        assert output.get('availability') == 'access_application'

        output['availability'] = 'contact_owner'

        # UPDATE AVAILABILITY AGAIN

        output = call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey,
                                 status=200, **output)
        assert 'id' in output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=output['id'])

        assert 'access_application_URL' not in output
        assert output.get('direct_download_URL') == settings.DATASET_URL_UNKNOWN, output['direct_download_URL']

        assert output.get('availability') == 'contact_owner'

    def test_field_clearing(self):
        '''
        Test that value None will remove a field completely
        '''
        data_dict = copy.deepcopy(TEST_DATADICT)
        data_dict['discipline'] = None

        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **data_dict)
        assert 'id' in output

        data_dict['id'] = output['id']
        data_dict['discipline'] = 'Matematiikka'

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=data_dict['id'])
        assert 'discipline' not in output

        call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey,
                        status=200, **data_dict)
        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=data_dict['id'])
        assert 'discipline' in output

        data_dict['discipline'] = None

        call_action_api(self.app, 'package_update', apikey=self.normal_user.apikey,
                        status=200, **data_dict)
        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=data_dict['id'])
        assert 'discipline' not in output


    def test_create_and_read_resource(self):
        '''
        Create and read resource data through API and test that 'url' matches. Availability 'through_provider'.
        '''
        data_dict = copy.deepcopy(TEST_DATADICT)
        data_dict['availability'] = 'through_provider'
        data_dict['through_provider_URL'] = 'http://www.tdata.fi/'
        data_dict.pop('direct_download_URL')

        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **data_dict)
        assert 'id' in output

        new_res = copy.deepcopy(TEST_RESOURCE)
        new_res['package_id'] = output['id']

        output = call_action_api(self.app, 'resource_create', apikey=self.normal_user.apikey,
                                 status=200, **new_res)
        assert output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=new_res['package_id'])
        assert 'id' in output

        resources = output.get('resources')
        assert len(resources) == 2
        assert resources[0]['url'] == TEST_RESOURCE['url'] or \
            resources[1]['url'] == TEST_RESOURCE['url'], resources[0]['url'] + ' --- ' + resources[1]['url']

    def test_create_and_read_resource2(self):
        '''
        Create and read resource data through API and test that 'url' matches. Availability 'direct_download'.
        Test with sysadmin user.
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                 status=200, **TEST_DATADICT)
        assert 'id' in output

        new_res = copy.deepcopy(TEST_RESOURCE)
        new_res['package_id'] = output['id']

        output = call_action_api(self.app, 'resource_create', apikey=self.normal_user.apikey,
                                 status=200, **new_res)
        assert output

        output = call_action_api(self.app, 'package_show', apikey=self.normal_user.apikey,
                                 status=200, id=new_res['package_id'])
        assert 'id' in output

        resources = output.get('resources')
        assert len(resources) == 2
        assert resources[0]['url'] == TEST_RESOURCE['url'] or \
            resources[1]['url'] == TEST_RESOURCE['url'], resources[0]['url'] + ' --- ' + resources[1]['url']

    def test_create_and_read_resource3(self):
        '''
        Create and delete a resource data through API and test that dataset still matches.
        '''
        output = call_action_api(self.app, 'package_create', apikey=self.sysadmin_user.apikey,
                                 status=200, **TEST_DATADICT)
        assert 'id' in output

        new_res = copy.deepcopy(TEST_RESOURCE)
        new_res['package_id'] = output['id']

        output = call_action_api(self.app, 'resource_create', apikey=self.sysadmin_user.apikey,
                                 status=200, **new_res)

        call_action_api(self.app, 'resource_delete', apikey=self.sysadmin_user.apikey,
                        status=200, id=output['id'])

        output = call_action_api(self.app, 'package_show', apikey=self.sysadmin_user.apikey,
                                 status=200, id=new_res['package_id'])
        assert 'id' in output

        assert self._compare_datadicts(output)


class TestSchema(KataApiTestCase):
    '''
    Test that schema works like it's supposed to.
    '''

    def test_all_required_fields(self):
        '''
        Remove each of Kata's required fields from a complete data_dict and make sure we get a validation error.
        '''
        # Hide validation error message which cannot be silenced with nosetest parameters. Has to be done here.
        logg = logging.getLogger('ckan.controllers.api')
        logg.disabled = True

        fields = settings.KATA_FIELDS_REQUIRED
        fields.pop(fields.index('contact_phone'))   # TODO: This will be removed
        fields.pop(fields.index('contact_URL'))     # TODO: This will be removed

        for requirement in fields:
            print requirement
            data = TEST_DATADICT.copy()
            data.pop(requirement)

            output = call_action_api(self.app, 'package_create', apikey=self.normal_user.apikey,
                                     status=409, **data)
            assert '__type' in output
            assert output['__type'] == 'Validation Error'

        logg.disabled = False

