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

from scripts.file_utils import replace_text
import shutil, os, re, glob
import json


def get_config_file(config_dir, version):
    return os.path.join(config_dir, f"FA{version}.json")


class LaunguageHandlerBase:
    def __init__(self):
        pass

    def generate_configs(self, config_dir, language, versions, artifact_version):
        """Generate the config files used for this language for each version"""
        pass

    def post_process(self, version, generator_output_dir, working_dir, build_output_root_dir, artifact_version,
                     first_version=False):
        """
        Run any post-processing required on generated code

        :param generator_output_dir: directory containing the generator output for this version
        :param working_dir: temp directory for staging work
        :param build_output_root_dir: target directory for output packages
        :param artifact_version: version of this artifact for package managers
        :param first_version: True if this is the first version generated. Useful for tasks that only
        need to be run once for all versions

        :return:
        """
        pass


class JavaHandler(LaunguageHandlerBase):
    def __init__(self):
        super().__init__()
        self.common_artifact_id = 'purestorage-rest-client-common'

    @staticmethod
    def get_artifact_id(version):
        return f"flasharray-rest-{version}-client"

    @staticmethod
    def get_model_package(version):
        return f"com.purestorage.rest.flasharray.v{version.replace('.', '_')}.model"

    @staticmethod
    def get_api_package(version):
        return f"com.purestorage.rest.flasharray.v{version.replace('.', '_')}.api"

    @staticmethod
    def fix_java_compilation_issues(directory):
        for entry in os.listdir(directory):
            filename = os.path.join(directory, entry)
            if os.path.isfile(filename):
                file, extension = os.path.splitext(entry)
                if file.startswith('Array') and extension == '.java':
                    replace_text(filename, r"import java.util.Arrays\;", "")
                if extension == '.java':
                    replace_text(filename, r"@javax.annotation.Generated.+", "")

            elif os.path.isdir(filename):
                JavaHandler.fix_java_compilation_issues(filename)

    def add_common_dependency_to_pom(self, pom_file, artifact_version):
        with open(pom_file, 'r+') as fd:
            contents = fd.readlines()
            for index, line in enumerate(contents):
                if '<dependencies>' in line:
                    contents.insert(index + 1, '        <dependency>\n')
                    contents.insert(index + 2, '            <groupId>com.purestorage</groupId>\n')
                    contents.insert(index + 3, f'            <artifactId>{self.common_artifact_id}</artifactId>\n')
                    contents.insert(index + 4, f'            <version>{artifact_version}</version>\n')
                    contents.insert(index + 5, '        </dependency>\n')
                    break
            fd.seek(0)
            fd.writelines(contents)

    def generate_configs(self, config_dir, language, versions, artifact_version):
        """Generate the config files used for this language for each version"""
        # Write configs
        for version in versions:
            config_dict = {
                'groupId': "com.purestorage",
                'invokerPackage': "com.purestorage.rest.common",
                'modelPackage': self.get_model_package(version),
                'apiPackage': self.get_api_package(version),
                'artifactId': self.get_artifact_id(version),
                'artifactVersion': artifact_version
            }
            with open(get_config_file(config_dir, version), 'w') as config_file:
                json.dump(config_dict, config_file)
        pass

    def post_process(self, version, generator_output_dir, working_dir, build_output_root_dir, artifact_version,
                     first_version=False):
        """
        Run any post-processing required on generated code

        :param generator_output_dir: directory containing the generator output for this version
        :param working_dir: temp directory for staging work
        :param build_output_root_dir: target directory for output packages
        :param artifact_version: version of this artifact for package managers
        :param first_version: True if this is the first version generated. Useful for tasks that only
        need to be run once for all versions

        :return:
        """
        print("Fixing Java compilation issues")
        self.fix_java_compilation_issues(working_dir)

        if first_version:
            print("Extracting common classes")
            # Copy out the common java files to a separate java project
            common_path = os.path.join(working_dir, "common")
            shutil.copytree(generator_output_dir, common_path, dirs_exist_ok=True)
            shutil.rmtree(os.path.join(common_path, "src", "main", "java", "com", "purestorage", "rest", "flasharray"))
            shutil.rmtree(os.path.join(common_path, "src", "test"))
            replace_text(os.path.join(common_path, 'pom.xml'), self.get_artifact_id(version), self.common_artifact_id)
            replace_text(
                os.path.join(common_path, "src", "main", "java", "com", "purestorage", "rest", "common", "JSON.java"),
                f"import {self.get_model_package(version)}.*;", "")
            common_target_path = os.path.join(build_output_root_dir, "common")
            os.makedirs(common_target_path)
            shutil.copytree(common_path, common_target_path, dirs_exist_ok=True)

            print("Common classes available at: " + common_target_path)

        shutil.rmtree(os.path.join(generator_output_dir, "src", "main", "java", "com", "purestorage", "rest", "common"))
        self.add_common_dependency_to_pom(os.path.join(generator_output_dir, 'pom.xml'), artifact_version)


def get_language_handler(language: str) -> LaunguageHandlerBase:
    if language == 'java':
        return JavaHandler()

    return LaunguageHandlerBase()
