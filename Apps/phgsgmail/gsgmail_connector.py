# File: gsgmail_connector.py
# Copyright (c) 2017-2021 Splunk Inc.
#
# Licensed under Apache 2.0 (https://www.apache.org/licenses/LICENSE-2.0.txt)


# Phantom App imports
import phantom.app as phantom
from phantom.base_connector import BaseConnector
from phantom.action_result import ActionResult
import phantom.utils as ph_utils

from gsgmail_consts import *
from bs4 import UnicodeDammit
from google.oauth2 import service_account

# Fix to add __init__.py in dependencies folder
import os
import requests
import json
import sys

init_path = '{}/dependencies/google/__init__.py'.format(  # noqa
    os.path.dirname(os.path.abspath(__file__))  # noqa
)  # noqa
try:  # noqa
    open(init_path, 'a+').close()  # noqa
except:  # noqa
    pass  # noqa

# the following argv 'work around' is to keep apiclient happy
# and _also_ debug the connector as a script via pudb
try:
    argv_temp = list(sys.argv)
except:
    pass
sys.argv = ['']

import apiclient  # noqa


class RetVal2(tuple):
    def __new__(cls, val1, val2=None):
        return tuple.__new__(RetVal2, (val1, val2))


#  Define the App Class
class GSuiteConnector(BaseConnector):

    def __init__(self):

        self._key_dict = None
        self._domain = None

        # Call the BaseConnectors init first
        super(GSuiteConnector, self).__init__()

    def _create_service(self, action_result, scopes, api_name, api_version, delegated_user=None):

        # first the credentials
        try:
            credentials = service_account.Credentials.from_service_account_info(self._key_dict, scopes=scopes)
        except Exception as e:
            return RetVal2(action_result.set_status(phantom.APP_ERROR, GSGMAIL_SERVICE_KEY_FAILURE,
                self._get_error_message_from_exception(e)), None)

        if (delegated_user):
            try:
                credentials = credentials.with_subject(delegated_user)
            except Exception as e:
                return RetVal2(action_result.set_status(phantom.APP_ERROR, GSGMAIL_CREDENTIALS_FAILURE,
                    self._get_error_message_from_exception(e)), None)

        try:
            service = apiclient.discovery.build(api_name, api_version, credentials=credentials)
        except Exception as e:
            return RetVal2(action_result.set_status(phantom.APP_ERROR,
                "Failed to create service object for API: {0}-{1}. {2} {3}".format(api_name, api_version, self._get_error_message_from_exception(e),
                    "Please make sure the user '{0}' is valid and the service account has the proper scopes enabled.".format(delegated_user)), None))

        return RetVal2(phantom.APP_SUCCESS, service)

    def initialize(self):

        # Fetching the Python major version
        try:
            self._python_version = int(sys.version_info[0])
        except:
            return self.set_status(phantom.APP_ERROR, "Error occurred while fetching the Phantom server's Python major version")

        config = self.get_config()

        key_json = config["key_json"]

        try:
            self._key_dict = json.loads(key_json)
        except Exception as e:
            return self.set_status(phantom.APP_ERROR, "Unable to load the key json", self._get_error_message_from_exception(e))

        self._login_email = config['login_email']

        if (not ph_utils.is_email(self._login_email)):
            return self.set_status(phantom.APP_ERROR, "Asset config 'login_email' failed validation")

        try:
            _, _, self._domain = self._login_email.partition('@')
        except Exception:
            return self.set_status(phantom.APP_ERROR, "Unable to extract domain from login_email")

        return phantom.APP_SUCCESS

    def _handle_py_ver_compat_for_input_str(self, input_str, always_encode=False):
        """
        This method returns the encoded|original string based on the Python version.
        :param input_str: Input string to be processed
        :param always_encode: Used if the string needs to be encoded for python 3
        :return: input_str (Processed input string based on following logic 'input_str - Python 3; encoded input_str - Python 2')
        """

        try:
            if input_str and (self._python_version == 2 or always_encode):
                input_str = UnicodeDammit(input_str).unicode_markup.encode('utf-8')
        except:
            self.debug_print("Error occurred while handling python 2to3 compatibility for the input string")

        return input_str

    def _validate_integer(self, action_result, parameter, key, allow_zero=False):
        if parameter is not None:
            try:
                if not float(parameter).is_integer():
                    return action_result.set_status(phantom.APP_ERROR, GSGMAIL_INVALID_INTEGER_ERR_MSG.format(msg="", param=key)), None

                parameter = int(parameter)
            except:
                return action_result.set_status(phantom.APP_ERROR, GSGMAIL_INVALID_INTEGER_ERR_MSG.format(msg="", param=key)), None

            if parameter < 0:
                return action_result.set_status(phantom.APP_ERROR, GSGMAIL_INVALID_INTEGER_ERR_MSG.format(msg="non-negative", param=key)), None
            if not allow_zero and parameter == 0:
                return action_result.set_status(phantom.APP_ERROR, GSGMAIL_INVALID_INTEGER_ERR_MSG.format(msg="non-zero positive", param=key)), None

        return phantom.APP_SUCCESS, parameter

    def _get_error_message_from_exception(self, e):
        """ This method is used to get appropriate error message from the exception.
        :param e: Exception object
        :return: error message
        """
        error_code = GSGMAIL_ERR_CODE_UNAVAILABLE
        error_msg = GSGMAIL_ERR_MESSAGE_UNAVAILABLE

        try:
            if e.args:
                if len(e.args) > 1:
                    error_code = e.args[0]
                    error_msg = e.args[1]
                    try:
                        error_json = json.loads(error_msg)
                        error = error_json.get('error')
                        if error:
                            if error.get('message'):
                                error_msg = error.get('message')
                            if error.get('code'):
                                error_code = error.get('code')
                    except:
                        pass
                elif len(e.args) == 1:
                    error_code = GSGMAIL_ERR_CODE_UNAVAILABLE
                    error_msg = e.args[0]
            else:
                error_code = GSGMAIL_ERR_CODE_UNAVAILABLE
                error_msg = GSGMAIL_ERR_MESSAGE_UNAVAILABLE
        except:
            error_code = GSGMAIL_ERR_CODE_UNAVAILABLE
            error_msg = GSGMAIL_ERR_MESSAGE_UNAVAILABLE

        try:
            error_msg = self._handle_py_ver_compat_for_input_str(error_msg)
        except TypeError:
            error_msg = GSGMAIL_UNICODE_DAMMIT_TYPE_ERROR_MESSAGE
        except:
            error_msg = GSGMAIL_ERR_MESSAGE_UNAVAILABLE

        return "Error Code: {0}. Error Message: {1}".format(error_code, error_msg)

    def _get_email_details(self, action_result, email_addr, email_id, service):

        """
        import web_pdb
        web_pdb.set_trace()
        """

        kwargs = { 'userId': email_addr, 'id': email_id, 'format': 'metadata' }

        try:
            email_details = service.users().messages().get(**kwargs).execute()
        except Exception as e:
            return RetVal2(action_result.set_status(phantom.APP_ERROR, GSGMAIL_EMAIL_FETCH_FAILURE,
                self._get_error_message_from_exception(e)))

        return RetVal2(phantom.APP_SUCCESS, email_details)

    def _map_email_details(self, input_email):

        """
        import web_pdb
        web_pdb.set_trace()
        """

        # The dictionary of header values
        header_dict = dict()

        # list of values that are to be extracted
        headers_to_parse = ['subject', 'delivered-to', 'from', 'to', 'message-id']

        # get the payload
        email_headers = input_email.pop('payload', {}).get('headers')

        if (not email_headers):
            return input_email

        for x in email_headers:

            if (not headers_to_parse):
                break

            header_name = x.get('name')
            header_value = x.get('value', '')

            if (not header_name):
                continue

            if (header_name.lower() not in headers_to_parse):
                continue

            key_name = header_name.lower().replace('-', '_')
            header_dict[key_name] = header_value

            headers_to_parse.remove(header_name.lower())

        input_email.update(header_dict)

        return (phantom.APP_SUCCESS, input_email)

    def _handle_run_query(self, param):

        # Implement the handler here, some basic code is already in

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Create the credentials with the required scope
        scopes = ['https://www.googleapis.com/auth/gmail.readonly']

        # Create a service here
        self.save_progress("Creating GMail service object")

        user_email = param['email']

        ret_val, service = self._create_service(action_result, scopes, "gmail", "v1", user_email)

        if (phantom.is_fail(ret_val)):
            return action_result.get_status()

        # create the query string
        query_string = ""

        if ('label' in param):
            query_string += " label:{0}".format(self._handle_py_ver_compat_for_input_str(param['label']))

        if ('subject' in param):
            query_string += " subject:{0}".format(self._handle_py_ver_compat_for_input_str(param['subject']))

        if ('sender' in param):
            query_string += " from:{0}".format(param['sender'])

        if ('internet_message_id' in param):
            query_string += " rfc822msgid:{0}".format(self._handle_py_ver_compat_for_input_str(param['internet_message_id']))

        if ('body' in param):
            query_string += " {0}".format(self._handle_py_ver_compat_for_input_str(param['body']))

        # if query is present, then override everything
        if ('query' in param):
            query_string = self._handle_py_ver_compat_for_input_str(param['query'])

        """
        # Check if there is something present in the query string
        if (not query_string):
            return action_result.set_status(phantom.APP_ERROR, "Please specify at-least one search criteria")
        """

        ret_val, max_results = self._validate_integer(
            action_result,
            param.get('max_results', 100),
            "max_results")
        if phantom.is_fail(ret_val):
            return action_result.get_status()

        kwargs = { 'maxResults': max_results, 'userId': user_email, 'q': query_string }

        page_token = self._handle_py_ver_compat_for_input_str(param.get('page_token'))
        if (page_token):
            kwargs.update({'pageToken': page_token})

        try:
            messages_resp = service.users().messages().list(**kwargs).execute()
        except Exception as e:
            return action_result.set_status(phantom.APP_ERROR, "Failed to get messages", self._get_error_message_from_exception(e))

        messages = messages_resp.get('messages', [])
        next_page = messages_resp.get('nextPageToken')
        summary = action_result.update_summary({'total_messages_returned': len(messages)})

        for curr_message in messages:

            curr_email_ar = ActionResult()

            ret_val, email_details_resp = self._get_email_details(curr_email_ar, user_email, curr_message['id'], service)

            if (phantom.is_fail(ret_val)):
                continue

            ret_val, email_details_resp = self._map_email_details(email_details_resp)

            if (phantom.is_fail(ret_val)):
                continue

            action_result.add_data(email_details_resp)

        if (next_page):
            summary['next_page_token'] = next_page

        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_delete_email(self, param):

        # Implement the handler here, some basic code is already in

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Create the credentials with the required scope
        scopes = ['https://mail.google.com/']

        # Create a service here
        self.save_progress("Creating GMail service object")

        user_email = param['email']

        ret_val, service = self._create_service(action_result, scopes, "gmail", "v1", user_email)

        if (phantom.is_fail(ret_val)):
            return action_result.get_status()

        email_ids = [x.strip() for x in param['id'].split(',')]
        email_ids = list(filter(None, email_ids))
        if not email_ids:
            return action_result.set_status(phantom.APP_ERROR, "Please provide valid value for 'id' action parameter")

        good_ids = set()
        bad_ids = set()

        for email_id in email_ids:
            kwargs = {
                'id': email_id,
                'userId': user_email
            }
            try:
                get_msg_resp = service.users().messages().get(**kwargs).execute()  # noqa
            except apiclient.errors.HttpError:
                self.debug_print("Caught HttpError")
                bad_ids.add(email_id)
                continue
            except Exception as e:
                self.debug_print("Exception name: {}".format(e.__class__.__name__))
                error_message = self._get_error_message_from_exception(e)
                return action_result.set_status(
                    phantom.APP_ERROR, 'Error checking email. ID: {} Reason: {}.'.format(email_id, error_message)
                )
            good_ids.add(email_id)

        if not good_ids:
            summary = action_result.update_summary({})
            summary['deleted_emails'] = list(good_ids)
            summary['ignored_ids'] = list(bad_ids)
            return action_result.set_status(
                phantom.APP_SUCCESS,
                "All the provided emails were already deleted, Ignored Ids : {}".format(summary['ignored_ids'])
            )

        kwargs = { 'body': { 'ids': email_ids }, 'userId': user_email }

        try:
            service.users().messages().batchDelete(**kwargs).execute()
        except Exception as e:
            return action_result.set_status(phantom.APP_ERROR, "Failed to delete messages", self._get_error_message_from_exception(e))

        summary = action_result.update_summary({})
        summary['deleted_emails'] = list(good_ids)
        summary['ignored_ids'] = list(bad_ids)

        return action_result.set_status(
            phantom.APP_SUCCESS,
            "Messages deleted, Ignored Ids : {}".format(summary['ignored_ids'])
        )

    def _handle_get_users(self, param):

        # Implement the handler here, some basic code is already in

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Create the credentials with the required scope
        scopes = ['https://www.googleapis.com/auth/admin.directory.user']

        # Create a service here
        self.save_progress("Creating AdminSDK service object")

        ret_val, service = self._create_service(action_result, scopes, "admin", "directory_v1", self._login_email)

        if (phantom.is_fail(ret_val)):
            return action_result.get_status()

        self.save_progress("Getting list of users for domain: {0}".format(self._domain))

        ret_val, max_users = self._validate_integer(
            action_result,
            param.get('max_items', 500),
            "max_items")
        if phantom.is_fail(ret_val):
            return action_result.get_status()

        kwargs = {'domain': self._domain, 'maxResults': max_users, 'orderBy': 'email', 'sortOrder': 'ASCENDING'}

        page_token = self._handle_py_ver_compat_for_input_str(param.get('page_token'))
        if (page_token):
            kwargs.update({'pageToken': page_token})

        try:
            users_resp = service.users().list(**kwargs).execute()
        except Exception as e:
            error_message = self._get_error_message_from_exception(e)
            self.debug_print("Exception message: {}".format(error_message))
            return action_result.set_status(phantom.APP_ERROR, GSGMAIL_USERS_FETCH_FAILURE, error_message)

        users = users_resp.get('users', [])
        num_users = len(users)
        next_page = users_resp.get('nextPageToken')
        summary = action_result.update_summary({'total_users_returned': num_users})

        for curr_user in users:
            action_result.add_data(curr_user)

        if (next_page):
            summary['next_page_token'] = next_page

        return action_result.set_status(phantom.APP_SUCCESS)

    def _handle_test_connectivity(self, param):

        self.save_progress("In action handler for: {0}".format(self.get_action_identifier()))

        # Add an action result object to self (BaseConnector) to represent the action for this param
        action_result = self.add_action_result(ActionResult(dict(param)))

        # Create the credentials, with minimal scope info for test connectivity
        scopes = ['https://www.googleapis.com/auth/admin.directory.user']

        # Test connectivity does not return any data, it's the status that is more important
        # and the progress messages
        # Create a service here
        self.save_progress("Creating AdminSDK service object")
        ret_val, service = self._create_service(action_result, scopes, "admin", "directory_v1", self._login_email)

        if (phantom.is_fail(ret_val)):
            self.save_progress("Test Connectivity Failed")
            return action_result.get_status()

        self.save_progress("Getting list of users for domain: {0}".format(self._domain))

        try:
            service.users().list(domain=self._domain, maxResults=1, orderBy='email', sortOrder="ASCENDING").execute()
        except Exception as e:
            self.save_progress("Test Connectivity Failed")
            return action_result.set_status(phantom.APP_ERROR, "Failed to get users", self._get_error_message_from_exception(e))

        # Return success
        self.save_progress("Test Connectivity Passed")
        return action_result.set_status(phantom.APP_SUCCESS)

    def handle_action(self, param):

        """
        import web_pdb
        web_pdb.set_trace()
        """

        ret_val = phantom.APP_SUCCESS

        # Get the action that we are supposed to execute for this App Run
        action_id = self.get_action_identifier()

        self.debug_print("action_id", self.get_action_identifier())

        if action_id == 'run_query':
            ret_val = self._handle_run_query(param)
        elif action_id == 'delete_email':
            ret_val = self._handle_delete_email(param)
        elif action_id == 'get_users':
            ret_val = self._handle_get_users(param)
        elif action_id == 'test_connectivity':
            ret_val = self._handle_test_connectivity(param)

        return ret_val


if __name__ == '__main__':

    import pudb
    import argparse

    pudb.set_trace()

    argparser = argparse.ArgumentParser()

    argparser.add_argument('input_test_json', help='Input Test JSON file')
    argparser.add_argument('-u', '--username', help='username', required=False)
    argparser.add_argument('-p', '--password', help='password', required=False)

    args = argv_temp.parse_args()
    session_id = None

    username = args.username
    password = args.password

    if (username is not None and password is None):

        # User specified a username but not a password, so ask
        import getpass
        password = getpass.getpass("Password: ")

    if (username and password):
        try:
            print("Accessing the Login page")
            login_url = BaseConnector._get_phantom_base_url() + 'login'
            r = requests.get(login_url, verify=False)
            csrftoken = r.cookies['csrftoken']

            data = dict()
            data['username'] = username
            data['password'] = password
            data['csrfmiddlewaretoken'] = csrftoken

            headers = dict()
            headers['Cookie'] = 'csrftoken=' + csrftoken
            headers['Referer'] = login_url

            print("Logging into Platform to get the session id")
            r2 = requests.post(login_url, verify=False, data=data, headers=headers)
            session_id = r2.cookies['sessionid']
        except Exception as e:
            print("Unable to get session id from the platfrom. Error: " + str(e))
            exit(1)

    with open(args.input_test_json) as f:
        in_json = f.read()
        in_json = json.loads(in_json)
        print(json.dumps(in_json, indent=4))

        connector = GSuiteConnector()
        connector.print_progress_message = True

        if (session_id is not None):
            in_json['user_session_token'] = session_id
            connector._set_csrf_info(csrftoken, headers['Referer'])

        ret_val = connector._handle_action(json.dumps(in_json), None)
        print(json.dumps(json.loads(ret_val), indent=4))

    exit(0)
