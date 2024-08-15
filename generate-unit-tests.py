import os
import subprocess
import re
import argparse
from prompt_template import NEW_TEST_SUITE_PROMPT_TEMPLATE, MODIFY_TEST_SUITE_PROMPT_TEMPLATE, FAILED_TESTS_PROMPT_TEMPLATE
from services.bedrock_service import BedrockService

def parse_cli_arguments():
    parser = argparse.ArgumentParser()

    parser.add_argument('--test-path', type=str, help="Path to existing unit tests")
    parser.add_argument('--test-command', type=str, default="pipenv run python -m unittest", help="Command to run unit tests")
    parser.add_argument('--dirs-to-test', nargs='+', help="directories to test")
    parser.add_argument('--test-prefix', type=str, default="test_", help="prefix for test paths")
    parser.add_argument('--max-cycles', type=int, default=3, help="maximum number of attempts AI will make at generating passing tests")
    parser.add_argument('--generated-test-path', type=str, default="test/ai_test/", help="path to AI generated unit tests")

    return parser.parse_args()

def get_current_branch():
    try:
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            check=True,
            text=True,
            capture_output=True
        )
        return result.stdout.strip("\n")
    except subprocess.CalledProcessError as e:
        print(f'Error: {e.stderr}')
        return None


def check_modified_path_is_of_interest(path, dirs_to_test):
    path = os.path.normpath(path)
    dirs_to_test = [os.path.normpath(dir) for dir in dirs_to_test]

    return any(os.path.commonpath([path, dir]) == dir for dir in dirs_to_test)


def get_modified_paths(dirs_to_test):
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', "main"],
            check=True,
            text=True,
            capture_output=True
        )
        return [path for path in result.stdout.split("\n") if check_modified_path_is_of_interest(path, dirs_to_test)]
    except subprocess.CalledProcessError as e:
        print(f'Error: {e.stderr}')
        return None


def validate_source_file_path(source_file_path):
    if not os.path.isfile(source_file_path):
        raise FileNotFoundError(f"Source file not found at {source_file_path}")


def validate_test_file_path(path):
    return os.path.isfile(path)


def get_file_diff(path):
    try:
        result = subprocess.run(
            ['git', 'diff', "main", '--function-context', path],
            check=True,
            text=True,
            capture_output=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f'Error: {e.stderr}')
        return None


def extract_function_name(function_str):
    match = re.search(r'\s*def\s+([a-zA-Z_][a-zA-Z_0-9]*)\s*\(', function_str)

    if match:
        return match.group(1)

    return None


def find_new_functions(diff):
    return [extract_function_name(line) for line in diff.split("\n") if "def" in line and line.startswith("+") and "__init__" not in line]


def get_modified_function_names_from_diff(diff):
    functions = [function for function in re.split(r'(?=def\s)', diff) if "def" in function and "__init__" not in function]

    modified_function_names = []
    for function in functions:
        for line in function.split("\n"):
            if line.strip(" ") not in ["", "+", "-"] and line.startswith("+") or line.startswith("-"):
                modified_function_names.append(extract_function_name(function))
                break

    new_function_names = find_new_functions(diff)

    filter_out_new_functions = list(set(modified_function_names).difference(new_function_names))

    if len(filter_out_new_functions) > 0:
        return ", ".join(filter_out_new_functions)

    return "No existing functions have been modified."


def get_modified_function_names(path):
    diff = get_file_diff(path)
    modified_function_names = get_modified_function_names_from_diff(diff)

    return modified_function_names


def build_prompt(path, template="new_test_suite", test_path="", modified_function_names="", failed_tests=""):
    file_to_test_content = read_file_contents(path)
    unit_test_file_content = ""

    if test_path != "":
        unit_test_file_content = read_file_contents(test_path)

    if template == "new_test_suite":
        module = path.replace("/", ".").strip(".py")

        return NEW_TEST_SUITE_PROMPT_TEMPLATE.format(
            module=module,
            file_to_test_content=file_to_test_content
        )

    if template == "modify_test_suite":
        return MODIFY_TEST_SUITE_PROMPT_TEMPLATE.format(
            file_to_test_content=file_to_test_content,
            unit_test_file_content=unit_test_file_content,
            modified_function_names=modified_function_names
        )

    if template == "failed_tests":
        return FAILED_TESTS_PROMPT_TEMPLATE.format(
            file_to_test_content=file_to_test_content,
            unit_test_file_content=unit_test_file_content,
            failed_tests=failed_tests
        )

    return ""


def write_file_contents(path, generated_unit_tests):
    if os.path.isdir("/".join(path.split("/")[:-1])):
        with open(path, "w", encoding='utf-8') as file:
            file.write(generated_unit_tests)
    else:
        os.makedirs("/".join(path.split("/")[:-1]))

        with open(path, "w", encoding='utf-8') as file:
            file.write(generated_unit_tests)


def read_file_contents(path):
    if os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as file:
            return file.read()
    else:
        return ""


def run_test_suite(path, test_command):
    try:
        test_results = subprocess.run(test_command.split(" ") + [path], capture_output=True, text=True, check=True).stderr
    except subprocess.CalledProcessError as e:
        return e.stderr

    broken_down_test_results = test_results.split("======================================================================")

    failed_tests = "".join([test for test in broken_down_test_results if "test_raises_error_when_no_github_token" not in test and "fail" in test.lower() or "error" in test.lower()])

    return failed_tests


def generate_tests(prompt, test_path, test_command):
    bedrock_service = BedrockService()
    model = "claude"

    # use bedrock to generate unit test skeleton
    generated_unit_tests = bedrock_service.request_model_response_from_bedrock(prompt, model)

    # write tests to file
    write_file_contents(test_path, generated_unit_tests)

    # Run generated unit tests - return any failed tests
    failed_tests = run_test_suite(test_path, test_command)

    return failed_tests

def generate_test_path(path, test_path, test_prefix):
    if test_path:
        return test_path + test_prefix + path.split('/').pop()

    return "test/" + "/".join([f"test_{dir}" for dir in path.split("/")])

def main():
    args = parse_cli_arguments()

    subprocess.run(["git", "fetch"], capture_output=True, text=True, check=True)

    modified_files = get_modified_paths(args.dirs_to_test)

    for path in modified_files:
        print(f"Generating unit tests for {path}")

        test_path = generate_test_path(path, args.test_path, args.test_prefix)

        validate_source_file_path(path)

        # Check if test suite already exists and create prompt
        if validate_test_file_path(test_path):
            template = "modify_test_suite"
            modified_function_names = get_modified_function_names(path)

            prompt = build_prompt(path, template, test_path, modified_function_names)
        else:
            prompt = build_prompt(path)

        test_test_path = args.generated_test_path + test_path.split("/").pop()

        # generate unit tests for specified path
        failed_tests = generate_tests(prompt, test_test_path, args.test_command)

        max_cycles = args.max_cycles
        cycles = 1

        # send tests back to AI to correct if there are failures
        while len(failed_tests) > 0 and cycles < max_cycles:
            print(f"Generation {cycles} of the test suite has produced the following errors: {failed_tests}")

            cycles += 1

            print(f"Generating generation {cycles} of the test suite")

            template = "failed_tests"
            prompt = build_prompt(path, template, test_test_path, [], failed_tests)

            failed_tests = generate_tests(prompt, test_test_path, args.test_command)

        print("Unit test generation complete")

        if len(failed_tests) > 0:
            print(f"Final test suite still has failures: {failed_tests}")


if __name__ == "__main__":
    main()
