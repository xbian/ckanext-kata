#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Selenium tests for Kata.

Requirements:
    - Firefox installed
    - Xvfb installed
    - ONKI component needs to be in kata.ini ckan footer with HTTPS protocol

These must be installed manually, they are not part of the Kata RPM packages.

To run as apache user do these also:
    mkdir /var/www/.gnome2
    chown apache:apache /var/www/.gnome2/
    chown apache:apache /var/www/.mozilla/

These tests need CKAN to be running so they cannot be combined with normal tests. Also they use your
main CKAN database.

To run from pyenv:
    xvfb-run nosetests ckanext-kata/ckanext/kata/testselenium/test_selenium.py
or
    ./ckanext-kata/nose.sh selenium

"""

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, ElementNotVisibleException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.common.by import By
from unittest import TestCase
import time


class TestKataBasics(TestCase):
    """Some basic Selenium tests for Kata's user interface without logged in user."""

    @classmethod
    def setup_class(cls):
        """Initialize tests."""
        cls.browser = webdriver.Firefox()  # Get local session of firefox

    @classmethod
    def teardown_class(cls):
        """Uninitialize tests."""
        cls.browser.quit()


    def test_front_page_loads(self):
        """Test that Selenium can access the front page."""

        self.browser.get("https://localhost/")
        assert "Kata" in self.browser.title


    def test_navigation(self):
        """
        Test that Selenium can access the navigation and all are present.
        """
        # These tests are very clumsy and should be made more sane in the future

        self.browser.get("https://localhost/")
        #assert "Kata" in self.browser.title
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/dataset')]")
        except NoSuchElementException:
            assert 0, 'Search (dataset) navigation not found for anonymous user'
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/dataset/new')]")
        except NoSuchElementException:
            assert 0, 'Add dataset navigation not found for anonymous user'
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/about')]")
        except NoSuchElementException:
            assert 0, 'About navigation not found for anonymous user'
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/help')]")
        except NoSuchElementException:
            assert 0, 'Help navigation not found for anonymous user'
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/faq')]")
        except NoSuchElementException:
            assert 0, 'FAQ navigation not found for anonymous user'
        try:
            search = self.browser.find_element_by_xpath("//a[contains(@href, '/user/login')]")
        except NoSuchElementException:
            assert 0, 'Log in link not found for anonymous user'




class TestKataWithUser(TestCase):
    """Some basic Selenium tests for Kata's user interface with a logged in user."""

    @classmethod
    def setup_class(cls):
        """Initialize tests."""

        # Create a sysadmin user using paster. Required for adding an organization.
        args = ['paster', '--plugin=ckan', 'sysadmin', 'add', 'selenium_admin', '-c', '/etc/kata.ini']
        import subprocess
        process = subprocess.Popen(args, stdin=subprocess.PIPE)
        try:
            process.communicate(input='y')
            process.communicate(input="selenium\n")     # password
            process.communicate(input="selenium\n")
        except ValueError:
            # The user probably exists already
            pass


    @classmethod
    def teardown_class(cls):
        """Uninitialize tests."""
        pass

    def _register_user(self, reg_browser, username=u'seleniumuser', fullname=u'seleniumuser'):
        """Register a new user, will be logged in automatically."""

        reg_browser.get("https://localhost/en/user/register")

        username = username + str(int(time.time()*100))

        try:
            field = reg_browser.find_element_by_xpath("//input[@id='field-username']")
            field.send_keys(username)

            field = reg_browser.find_element_by_xpath("//input[@id='field-fullname']")
            field.send_keys(fullname)

            field = reg_browser.find_element_by_xpath("//input[@id='field-email']")
            field.send_keys('kata.selenium@gmail.com')

            field = reg_browser.find_element_by_xpath("//input[@id='field-password']")
            field.send_keys('seleniumuser')

            field = reg_browser.find_element_by_xpath("//input[@id='field-confirm-password']")
            field.send_keys('seleniumuser')

            btn = reg_browser.find_element_by_xpath("//button[@name='save']")
            btn.click()

        except NoSuchElementException:
            reg_browser.get_screenshot_as_file('_register_user.png')
            assert 0, "Error processing the user registration page"

        try:
            WebDriverWait(reg_browser, 30).until(expected_conditions.presence_of_element_located((By.XPATH, "//i[contains(@class, 'icon-signout')]")))
        except TimeoutException:
            reg_browser.get_screenshot_as_file('_register_user.png')
            reg_browser.quit()
            assert 0, "User registration didn't finish"



    def _add_dataset(self, browser):
        """
        Add a simple dataset. Return dataset address.
        """

        browser.get("https://localhost/en/dataset/new")
        browser.implicitly_wait(8)  # Wait for javascript magic to alter fields

        try:
            field = browser.find_element_by_xpath("//input[@id='langtitle__0__value_id']")
            field.send_keys('Selenium Dataset')

            field = browser.find_element_by_xpath("//input[@name='agent__2__name']")
            field.send_keys('Selenium')

            field = browser.find_element_by_xpath("//input[@name='agent__2__organisation']")
            field.send_keys('CSC Oy')

            # Keywords -- the actual autocomplete field lacks the id attribute, so find it through an ancestor's sibling
            field = browser.find_element_by_xpath("//input[@id='field-tags']/../div[@class='select2-container select2-container-multi']//input")
            field.send_keys('Selenium')
            field.send_keys(Keys.RETURN)

            field = browser.find_element_by_xpath("//input[@name='langdis']")
            field.click()

            #field = test_browser.find_elements_by_class_name('select2-input')[2]  # hopefully distributor name
            #field.send_keys('Selenium')
            #field.send_keys(Keys.RETURN)

            field = browser.find_element_by_xpath("//input[@id='contact__0__name']")
            field.send_keys('Selenium contact')
            field = browser.find_element_by_xpath("//input[@id='contact__0__email']")
            field.send_keys('kata.selenium@gmail.com')
            field = browser.find_element_by_xpath("//input[@id='contact__0__URL']")
            field.send_keys('https://localhost/')
            field = browser.find_element_by_xpath("//input[@id='contact__0__phone']")
            field.send_keys('+35891234567')

            # field = browser.find_element_by_xpath("//input[@name='projdis']")
            # field.click()
            #
            field = browser.find_element_by_xpath("//input[@id='contact_owner']")
            field.click()

            field = browser.find_element_by_xpath("//input[@name='agent__1__name']")
            field.send_keys('Selenium')

            #field = browser.find_element_by_xpath("//input[@id='licenseURL']")
            #field.send_keys('Shareware')
            #field.send_keys(Keys.ENTER)
            browser.find_element_by_xpath("//button[@name='save']").click()

        except NoSuchElementException:
            browser.get_screenshot_as_file('_add_dataset.png')
            assert 0, "Error processing the create dataset page"

        try:
            WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located((By.XPATH, "//article/div/a[.='Hide/show']")))
        except TimeoutException:
            browser.get_screenshot_as_file('_add_dataset.png')
            browser.quit()
            assert 0, "Dataset creation didn't finish"

        assert "Kata" in browser.title, "Dataset creation failed somehow"

        return ''.join(browser.current_url)


    def test_register_user(self):
        """
        Test for user registration.
        """
        browser = webdriver.Firefox()
        self._register_user(browser)
        browser.quit()


    def test_register_user_fullname_utf8(self):
        """
        Test for user registration with special characters.
        """
        browser = webdriver.Firefox()
        self._register_user(browser, username=u'selenium', fullname=u'АБВГДЕЁЖЗИЙ κόσμε...')
        browser.quit()


    def test_add_dataset_and_contact_form(self):
        """Test that user can go back from contact form and still go forward to send it."""

        browser = webdriver.Firefox()
        self._register_user(browser)

        dataset_url = self._add_dataset(browser)
        browser.quit()

        browser = webdriver.Firefox()  # Get a new session
        self._register_user(browser)

        assert dataset_url is not None, "dataset url not found"

        # Go to contact form
        contact_form_url = dataset_url.replace('/dataset/', '/contact/')
        browser.get(dataset_url)

        browser.get(contact_form_url)
        try:
            browser.find_element_by_xpath("//textarea[@name='msg']")
        except NoSuchElementException:
            browser.get_screenshot_as_file('test_2_contact_form_can_go_back.png')
            assert 0, 'Contact form expected but not found (first visit)'

        browser.back()
        browser.get(contact_form_url)
        browser.implicitly_wait(10)      # Wait for some javascript magic

        try:
            field = browser.find_element_by_xpath("//textarea[@name='msg']")
            field.send_keys('Selenium is a testing')

            btn = browser.find_element_by_xpath("//input[@value='Send']")
            btn.click()

        except NoSuchElementException:
            browser.get_screenshot_as_file('test_2_contact_form_can_go_back.png')
            assert 0, 'Contact form expected but not found (second visit)'

        try:
            WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located((By.XPATH, "//div[contains(text(),'Message sent')]")))
        except TimeoutException:
            browser.get_screenshot_as_file('test_2_contact_form_can_go_back.png')
            assert 0, "Sending contact form didn't finish"

        browser.quit()


    def test_navigation(self):
        """
        Test that navigation is ok for logged in user.
        """
        # These should match often twice, clumsy, fix in the future
        browser = webdriver.Firefox()
        self._register_user(browser)

        browser.get("https://localhost/")
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/dataset')]")
        except NoSuchElementException:
            assert 0, 'Search (dataset) navigation not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/dataset/new')]")
        except NoSuchElementException:
            assert 0, 'Add dataset navigation not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/about')]")
        except NoSuchElementException:
            assert 0, 'About navigation not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/help')]")
        except NoSuchElementException:
            assert 0, 'Help navigation not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/faq')]")
        except NoSuchElementException:
            assert 0, 'FAQ navigation not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/dashboard')]")
        except NoSuchElementException:
            assert 0, 'Notifications link not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/user/_logout')]")
        except NoSuchElementException:
            assert 0, 'Log out link not found for logged in user'
#        try:
#            search = browser.find_element_by_xpath("//a[contains(@href, '/#')]")
#        except NoSuchElementException:
#            assert 0, 'Drop down (profile menu) link not found for logged in user'
        try:
            search = browser.find_element_by_xpath("//a[contains(@href, '/user/selenium')]")
        except NoSuchElementException:
            assert 0, 'My datasets link not found for logged in user'

        browser.quit()


    def test_advanced_search(self):
        """Test that advanced search returns our shiny new dataset."""

        browser = webdriver.Firefox()
        self._register_user(browser)

        browser.get("https://localhost/en/dataset")

        try:
            btn = browser.find_element_by_xpath("//a[contains(@href, '#advanced-search-tab')]")
            btn.click()

        except NoSuchElementException:
            browser.get_screenshot_as_file('test_3_advanced_search.png')
            assert 0, 'Advanced search tab not found'

        try:
            WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located((By.ID, 'advanced-search-date-end')))
        except TimeoutException:
            browser.get_screenshot_as_file('test_3_advanced_search.png')
            assert 0, "Error switching to advanced search"

        try:
            field = browser.find_element_by_id("advanced-search-text-1")
            field.send_keys('Selenium')
            field.send_keys(Keys.ENTER)
        except NoSuchElementException:
            browser.get_screenshot_as_file('test_3_advanced_search.png')
            assert 0, 'Search text field not found'

        try:
            WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located((By.XPATH, "//footer")))
        except TimeoutException:
            browser.get_screenshot_as_file('test_3_advanced_search.png')
            assert 0, "Didn't get the expected search result"

        # As the Solr index seems to live it's own life and the database might not have been cleared,
        # we cannot be sure how many hits should be expected. So this works for 1 or more results.

        try:
            browser.find_element_by_xpath("//li/div/h3/a[contains(text(),'Selenium Dataset')]")
        except NoSuchElementException:
            assert 0, 'Selenium Dataset not found with advanced search'


        browser.quit()


    def test_logout(self):
        """
        Test logout for Selenium user.
        """

        browser = webdriver.Firefox()
        self._register_user(browser)

        browser.get("https://localhost/en/user/_logout")

        try:
            search = browser.find_element_by_xpath("//p[.='You are now logged out.']")
        except NoSuchElementException:
            browser.get_screenshot_as_file('test_9_test_logout.png')
            assert 0, "Error logging out"

        browser.quit()


    def _add_dataset_advanced(self, browser, dataset_list):
        """
        Create a dataset with values from argument dataset_list.

        dataset_list element format:
        (element_search_function, function_parameter, keyboard_input_to_element (or WebElement.click), wait_for)

        :return dataset url
        """

        browser.get("https://localhost/en/dataset/new")

        # TODO: rather wait for a certain element that the js creates
        browser.implicitly_wait(15)  # Wait for javascript magic to alter fields

        try:
            for (funct, param, values, wait_for) in dataset_list:

                print ("%r ( %r ) : %r " % (funct, param, values))
                field = funct(param)

                for value in values:
                    if value == WebElement.click:
                        field.click()
                    else:
                        field.send_keys(value)
                    if wait_for:
                        browser.implicitly_wait(wait_for)
                        #WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located(wait_for))

        except (NoSuchElementException, ElementNotVisibleException) as exception:
            browser.get_screenshot_as_file('_add_dataset_advanced.png')
            print exception
            assert 0, "Error processing the create dataset page"

        try:
            WebDriverWait(browser, 30).until(expected_conditions.presence_of_element_located((By.XPATH, "//article/div/a[.='Hide/show']")))
        except TimeoutException:
            browser.get_screenshot_as_file('_add_dataset_advanced.png')
            browser.quit()
            assert 0, "Dataset creation didn't finish, URL: %r" % browser.current_url

        assert "Kata" in browser.title, "Dataset creation failed somehow"

        return browser.current_url


    def test_add_dataset_all_fields(self):
        """Create a dataset with all fields filled."""

        browser = webdriver.Firefox()

        def find_select2_inputs(id):
            """
            Finds 'select2-input's
            """
            elements = browser.find_elements_by_class_name('select2-input')
            return elements[id]

        def find_select2_choice_inputs(id):
            """
            Finds 'select2-choice's
            """
            elements = browser.find_elements_by_class_name('select2-choice')
            return elements[id]

        def find_plus_buttons(id):
            """
            Finds '?' and '+' buttons
            """
            all_elements = browser.find_elements_by_class_name('kata-plus-btn')
            visible_elements = filter(lambda elem: elem.is_displayed(), all_elements)
            return visible_elements[id]

        # TODO: Use all fields.

        dataset_to_add = [
            # Add titles
            #(find_plus_buttons, 1, [Keys.SPACE], None),
            #(find_plus_buttons, 1, [Keys.SPACE], None),

            (browser.find_element_by_id, 'langtitle__0__value_id', [u'Advanced Selenium Dataset'], None),
            (browser.find_element_by_name, 'langtitle__0__lang', [u'en'], None),
            # (browser.find_element_by_id, 'title__1__value_id', [u'Selenium-tietoaineisto'], None),
            # (browser.find_element_by_name, 'title__1__lang', [u'fi'], None),
            # (browser.find_element_by_id, 'title__2__value_id', [u'Selenium ÅÄÖ'], None),
            # (browser.find_element_by_name, 'title__2__lang', [u'sv'], None),

            # Add authors
            #(find_plus_buttons, 3, [WebElement.click], None),
            #(find_plus_buttons, 3, [WebElement.click], None),

            (browser.find_element_by_name, 'agent__2__name', [u'Ascii Author'], None),
            (browser.find_element_by_name, 'agent__2__organisation', [u'CSC Oy'], None),
            #(browser.find_element_by_id, 'author__1__value_id', [u'Åke Author'], None),
            #(browser.find_element_by_id, 'organization__1__value_id', [u'Organization 2'], None),
            #(browser.find_element_by_id, 'author__2__value_id', [u'прстуфхцчшчьыъэюя Author'], None),
            #(browser.find_element_by_id, 'organization__2__value_id', [u'Organization 3'], None),

            # keywords
            (browser.find_element_by_xpath, "//input[@id='field-tags']/../div[@class='select2-container select2-container-multi']//input", ['Selenium', Keys.RETURN, 'Keyword2', Keys.RETURN], None),

            (browser.find_element_by_id, 'language', [u'eng, fin, swe, tlh'], None),

            (browser.find_element_by_id, 'contact__0__name', [u'Selenium'], None),
            (browser.find_element_by_id, 'contact__0__phone', [u'+35891234567'], None),
            (browser.find_element_by_id, 'contact__0__email', [u'kata.selenium@gmail.com'], None),
            (browser.find_element_by_id, 'contact__0__URL', [u'https://localhost/'], None),

            (browser.find_element_by_name, 'projdis', [WebElement.click], None),

            (browser.find_element_by_name, 'agent__0__organisation', [u'Selenium Project'], None),
            (browser.find_element_by_name, 'agent__0__name', [u'Selenium Funder'], None),
            (browser.find_element_by_name, 'agent__0__fundingid', [u'Selenium Funding'], None),
            (browser.find_element_by_name, 'agent__0__URL', [u'https://localhost/'], None),

            # (browser.find_element_by_id, 'project_name', [u'Selenium Project'], None),
            # (browser.find_element_by_id, 'project_funder', [u'Selenium Funder'], None),
            # (browser.find_element_by_id, 'project_funding', [u'Selenium Funding'], None),
            # (browser.find_element_by_id, 'project_homepage', [u'https://localhost/'], None),
            #
            (browser.find_element_by_name, 'agent__1__name', [u'прстуфхцчшчьыъэюя'], None),

            (browser.find_element_by_id, 'name-pid', [u'pid' + str(int(time.time() * 100))], None),
            (browser.find_element_by_name, 'new_version_pid', [u'pid' + str(int(time.time() * 100))], None),

            (browser.find_element_by_id, 'direct_download', [Keys.SPACE], None),
            (browser.find_element_by_id, 'direct_download_URL', [u'https://localhost/'], None),

            #(browser.find_element_by_id, 'licenseURL', [u'dada'], None),

            (browser.find_element_by_xpath, "//section[@id='recmod']/h2", [WebElement.click], None),
            # recommended info

            (browser.find_element_by_xpath, "//input[@id='geographic_coverage_field']/../div[@class='select2-container select2-container-multi']//input", [u'Espoo, Finland', Keys.RETURN], None),
            # (browser.find_element_by_id, 'geographic_coverage_field', [u'Espoo, Finland', Keys.RETURN], None),

            #(find_select2_choice_inputs, 2, ['Ultimate Selenium collection', Keys.ENTER], None),  # collection / series
            #(find_select2_choice_inputs, 2, ['Selenium discipline', Keys.RETURN], None),  # discipline

            (browser.find_element_by_xpath, "//input[@id='discipline_field']/../div[@class='select2-container select2-container-multi']//input", [u'Matematiikka', Keys.RETURN], None),
            # (browser.find_element_by_id, 'discipline_field', [u'Matematiikka', Keys.RETURN], None),

            (browser.find_element_by_xpath, "//input[@id='mimetype']/../div[@class='select2-container select2-container-multi']//input", [u'application/pdf', Keys.RETURN], None),
            (browser.find_element_by_id, 'checksum', [u'f60e586509d99944e2d62f31979a802f'], None),
            (browser.find_element_by_id, 'algorithm', [u'md5'], None),

            (browser.find_element_by_id, 'field-notes', [u'Some description about this dataset'], None),

            (browser.find_element_by_xpath, "//button[@name='save']", [WebElement.click], None)
        ]

        self._register_user(browser)

        dataset_url = self._add_dataset_advanced(browser, dataset_to_add)

        browser.quit()
