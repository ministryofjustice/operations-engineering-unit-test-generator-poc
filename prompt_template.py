COMMON_RULES = """
Rules:
- Tests must be written in Python using the unittest framework.
- Do not acknowledge the question asked.
- Do not include any extra information.
- Do not explain your answers.
- Only produce the test code, nothing else.
- Make sure that you are importing classes and function into the test script in the correct way,
for example, if I want to import the class "MyService" from the module "services.my_service" I would do it this way:
"from services.my_service import MyService".
- Do not include any markdown in the output e.g. ```python something ```
- Ensure constants are correctly imported: "from config.constants import MY_CONSTANT"
"""

EXAMPLE_SCRIPT = """
import boto3
import time
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

class CloudtrailService:
    def __init__(self) -> None:
        self.client = boto3.client("cloudtrail", region_name="eu-west-2")

    def get_active_users_for_dormant_users_process(self):
        username_key = "eventData.useridentity.principalid"
        data_store_id = "ec682140-3e75-40c0-8e04-f06207791c2e"
        period_cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')

        query_string = f\"\"\"
        SELECT DISTINCT {{username_key}}
        FROM {{data_store_id}}
        WHERE eventTime > '{{period_cutoff}}';
        \"\"\"

        query_id = self.client.start_query(QueryStatement=query_string)['QueryId']

        return self.get_query_results(query_id)

    # pylint: disable=W0719
    def get_query_results(self, query_id):
        while True:
            status = self.client.get_query_results(QueryId=query_id)['QueryStatus']
            print(f"Query status: {{status}}")
            if status in ['FAILED', 'CANCELLED', 'TIMED_OUT']:
                raise ClientError(
                    {{
                        'Error': {{
                            'Code': status,
                            'Message': f"Cloudtrail data lake query failed with status: {{status}}"
                        }}
                    }},
                    operation_name='get_query_results'
                )
            if status == 'FINISHED':
                return self.extract_query_results(query_id)
            time.sleep(20)

    def extract_query_results(self, query_id):
        response = self.client.get_query_results(QueryId=query_id, MaxQueryResults=1000)
        active_users = [list(row[0].values())[0] for row in response['QueryResultRows']]

        if "NextToken" in response:
            next_token = response["NextToken"]

            while True:
                response = self.client.get_query_results(QueryId=query_id, MaxQueryResults=1000, NextToken=next_token)
                active_users = active_users + [list(row[0].values())[0] for row in response['QueryResultRows']]
                if "NextToken" in response:
                    next_token = response["NextToken"]
                else:
                    break

        return active_users
"""

EXAMPLE_UNIT_TESTS = """
import unittest
import boto3
from unittest.mock import patch, MagicMock, call
from botocore.exceptions import ClientError
from moto import mock_aws
from services.cloudtrail_service import CloudtrailService
from freezegun import freeze_time

class TestCloudtrailService(unittest.TestCase):

    @mock_aws
    def setUp(self):
        self.cloudtrail_service = CloudtrailService()
        self.cloudtrail_service.client = boto3.client("cloudtrail", region_name="us-west-2")

    @freeze_time("2024-07-11 00:00:00")
    @patch.object(CloudtrailService, "get_query_results")
    @mock_aws
    def get_active_users_for_dormant_users_process(self, mock_query_results):
        mock_active_users = ["user1", "user2", "user3"]
        mock_query_results.return_value = mock_active_users
        self.cloudtrail_service.client.start_query = MagicMock()
        mock_query_string = \"\"\"
        SELECT DISTINCT eventData.useridentity.principalid
        FROM ec682140-3e75-40c0-8e04-f06207791c2e
        WHERE eventTime > '2024-04-12 00:00:00';
        \"\"\"

        assert self.cloudtrail_service.get_active_users_for_dormant_users_process() == mock_active_users
        self.cloudtrail_service.client.start_query.assert_called_once_with(QueryStatement=mock_query_string)

    @patch.object(CloudtrailService, "extract_query_results")
    @mock_aws
    def test_get_query_results_if_success(self, mock_extract_query_results):
        mock_active_users = ["user1", "user2", "user3"]
        mock_extract_query_results.return_value = mock_active_users
        self.cloudtrail_service.client.get_query_results = MagicMock(return_value={{'QueryStatus': 'FINISHED'}})
        mock_query_id = "mock_id"

        response = self.cloudtrail_service.get_query_results(mock_query_id)

        self.cloudtrail_service.client.get_query_results.assert_called_once_with(QueryId=mock_query_id)
        mock_extract_query_results.assert_called_once_with(mock_query_id)
        assert response == mock_active_users

    @mock_aws
    def test_get_query_results_if_fail(self):
        self.cloudtrail_service.client.get_query_results = MagicMock(return_value={{'QueryStatus': 'CANCELLED'}})
        with self.assertRaises(ClientError) as context:
            self.cloudtrail_service.get_query_results("mock_id")

        self.cloudtrail_service.client.get_query_results.assert_called_once_with(QueryId="mock_id")
        self.assertEqual(str(context.exception), "An error occurred (CANCELLED) when calling the get_query_results operation: Cloudtrail data lake query failed with status: CANCELLED")

    # pylint: disable=C0103, W0613
    @mock_aws
    def test_extract_query_results(self):
        mock_next_token = "mock_next_token"

        def mock_get_query_results(QueryId=None, MaxQueryResults=1000, NextToken=False):
            if NextToken:
                return {{'QueryResultRows': [[{{'principalId': 'test_user3'}}]]}}

            return {{'NextToken': mock_next_token, 'QueryResultRows': [[{{'principalId': 'test_user1'}}], [{{'principalId': 'test_user2'}}]]}}

        self.cloudtrail_service.client.get_query_results = MagicMock(side_effect=mock_get_query_results)
        mock_query_id = "mock_id"

        assert self.cloudtrail_service.extract_query_results(mock_query_id) == ["test_user1", "test_user2", "test_user3"]
        self.cloudtrail_service.client.get_query_results.assert_has_calls([call(QueryId=mock_query_id, MaxQueryResults=1000), call(QueryId=mock_query_id, MaxQueryResults=1000, NextToken=mock_next_token)])
"""

EXAMPLE = f"""
For example. given this script:

{EXAMPLE_SCRIPT}

This is the associated test suite:

{EXAMPLE_UNIT_TESTS}
"""

NEW_TEST_SUITE_PROMPT_TEMPLATE = """

Please write a new test suite, using the Python unittest framework, for the provided script:

{file_to_test_content}

Classes and functions should be imported into the test script from the following module reference: {module}

""" + EXAMPLE + COMMON_RULES

MODIFY_TEST_SUITE_PROMPT_TEMPLATE = """

This a a python script:

{file_to_test_content}

This is the current unit test suite for this script:

{unit_test_file_content}

Please update the unit tests for the following functions which have been recently modified:
{modified_function_names}

Do not modify any existing unit tests unless specified.

Please add tests to the current suite for functions in the script that do not have unit tests.

Do not create additional unit tests for functions that are already associated with unit tests.

Please respond with the complete new unit test suite.

""" + EXAMPLE + COMMON_RULES

FAILED_TESTS_PROMPT_TEMPLATE = """
This is the script that I am testing:

{file_to_test_content}

This is the current unit test suite for this script:

{unit_test_file_content}

These are the current unit test failures:
{failed_tests}

Please amend the failing tests so that they pass and return the new test suite.

Only modify the failing tests please.

Use mock_response.__getitem__.return_value to mock response["body"].
""" + COMMON_RULES
