# The sample script and documentation are provided AS IS and are not supported by
# the author or the author's employer, unless otherwise agreed in writing. You bear
# all risk relating to the use or performance of the sample script and documentation.
# The author and the author's employer disclaim all express or implied warranties
# (including, without limitation, any warranties of merchantability, title, infringement
# or fitness for a particular purpose). In no event shall the author, the author's employer
# or anyone else involved in the creation, production, or delivery of the scripts be liable
# for any damages whatsoever arising out of the use or performance of the sample script and
# documentation (including, without limitation, damages for loss of business profits,
# business interruption, loss of business information, or other pecuniary loss), even if
# such person has been advised of the possibility of such damages.

import argparse
import json
import subprocess
from typing import List
import tempfile, shutil, os, re, glob
import urllib.request

from scripts import yaml_utils


def determine_versions(source_dir, versions):
    # Determine Versions
    if (versions is None or len(versions) == 0):
        versions = []
        for entry in os.listdir(os.path.join(source_dir, "specs")):
            filename, extension = os.path.splitext(entry)
            if extension == '.yaml' and filename.endswith('.spec'):
                filename = filename[:-len('.spec')]
                if filename.startswith('FA2.') and (filename[4:] == 'X' or filename[4:].isdigit()):
                    versions.append(filename[2:])

    return versions


def get_config_file(config_dir, version):
    return os.path.join(config_dir, f"FA{version}.json")


def generate_configs(config_dir, language, versions):
    # Write configs
    os.mkdir(config_dir)
    for version in versions:
        if language == 'java':
            config_dict = {
                'modelPackage': f"com.purestorage.flasharray.rest{version.replace('.', '')}.model",
                'apiPackage': f"com.purestorage.flasharray.rest{version.replace('.', '')}.api",
                'artifactId': f"flasharray-rest-{version}-java-client"
            }
            with open(get_config_file(config_dir, version), 'w') as config_file:
                json.dump(config_dict, config_file)


def replace_text(filename, to_replace, replacement):
    with open(filename, "r") as file:
        lines = file.readlines()
    with open(filename, "w") as file:
        for line in lines:
            file.write(re.sub(to_replace, replacement, line))


def fix_camel_case_issues(directory):
    for entry in os.listdir(directory):
        filename = os.path.join(directory, entry)
        if os.path.isfile(filename):
            _, extension = os.path.splitext(entry)
            if extension == '.yaml':
                replace_text(filename, "KMIP", "Kmip")
                replace_text(filename, "SAML2 SSO", "Saml2Sso")
                replace_text(filename, "SAML2-SSO", "Saml2Sso")
                replace_text(filename, "SNMPAgent", "SnmpAgent")
                replace_text(filename, "APIClient", "ApiClient")
                replace_text(filename, "SMI-S", "Smis")
                replace_text(filename, "DNS", "Dns")

        elif os.path.isdir(filename):
            fix_camel_case_issues(filename)


def fix_array_imports(directory):
    for entry in os.listdir(directory):
        filename = os.path.join(directory, entry)
        if os.path.isfile(filename):
            file, extension = os.path.splitext(entry)
            if file.startswith('Array') and extension == '.java':
                replace_text(filename, r"import java.util.Arrays\;", "")
            if extension == '.java':
                replace_text(filename, r"@javax.annotation.Generated.+", "")

        elif os.path.isdir(filename):
            fix_array_imports(filename)


def build(source: str, target:str, language: str, versions: List[str], swagger_jar_url: str, java_binary: str):
    # Copy source files to temporary location
    temp_dir = tempfile.mkdtemp()
    print("Working in directory: " + temp_dir)

    print("Downloading " + swagger_jar_url)
    swagger_jar = os.path.join(temp_dir, 'swagger-codegen-cli.jar')
    urllib.request.urlretrieve(swagger_jar_url, swagger_jar)

    source_dir = os.path.join(temp_dir, 'source')
    config_dir = os.path.join(temp_dir, 'config')

    print("Making a copy of the swagger files")
    shutil.copytree(source, source_dir, dirs_exist_ok=True)

    versions = determine_versions(source_dir, versions)
    versions.sort()
    print("Generating config for versions: " + str(versions))
    generate_configs(config_dir, language, versions)
    print("Fixing camel case issues")
    fix_camel_case_issues(source_dir)

    # Process the yaml files for models and responses to make them work correctly with code generation
    print("Fixing references in models and responses")
    yaml_utils.process_paths(glob.glob(os.path.join(source_dir, 'models', 'FA*')))
    yaml_utils.process_paths(glob.glob(os.path.join(source_dir, 'responses', 'FA*')))

    for version in versions:
        target_path = os.path.join(target, f"{version}")
        if os.path.isdir(target_path) and len(os.listdir(target_path)) != 0:
            print("WARNING: Target directory not empty: " + target_path)
            print("WARNING: Skipping version: " + version)
            continue

        client_dir = os.path.join(temp_dir, f"client_{version}")
        os.mkdir(client_dir)

        print("Generating client for version " + version)
        result = subprocess.run([java_binary,
                                 '-jar',
                                 swagger_jar,
                                 'generate',
                                 '-i',
                                 os.path.join(source_dir, 'specs', f"FA{version}.spec.yaml"),
                                 '-o',
                                 client_dir,
                                 '-l',
                                 language,
                                 '-c',
                                 get_config_file(config_dir, version)],
                                capture_output=True,
                                text=True)

        try:
            result.check_returncode()
        except subprocess.CalledProcessError:
            print(result.stdout)
            print(result.stderr)
            raise

        if language == 'java':
            print("Fixing array import issue")
            fix_array_imports(client_dir)

        os.makedirs(target_path)
        shutil.copytree(client_dir, target_path, dirs_exist_ok=True)

        print("Generated SDK available at: " + target_path)

    print("Cleaning up")
    shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(description='Build FlashArray REST 2 SDK from swagger files')
    parser.add_argument('source', help='Location of Swagger spec files')
    parser.add_argument('target', help='Directory to put generated clients')
    parser.add_argument('--versions', '-v', nargs='+', help='List of versions to build. Omit to build all versions.', default=None, required=False)
    parser.add_argument('--language', '-l', help='Language to build. Defaults to "java".', default='java', required=False)
    parser.add_argument('--java-binary', '-j', help='Location of the Java binary. Defaults to "/usr/bin/java".', default='/usr/bin/java', required=False)
    parser.add_argument('--swagger-gen', '-s', help='URL of swagger-codegen-cli jar file.', default='https://repo1.maven.org/maven2/io/swagger/swagger-codegen-cli/2.4.28/swagger-codegen-cli-2.4.28.jar', required=False)

    args = parser.parse_args()

    if not os.path.isfile(args.java_binary):
        print("ERROR: --java-binary must be a path to a java executable")
        exit(1)


    build(args.source, args.target, args.language, args.versions, args.swagger_gen, args.java_binary)


if __name__ == '__main__':
    main()
