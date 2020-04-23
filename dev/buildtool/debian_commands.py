# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implements debian support commands for buildtool."""

import os
import re

from buildtool import (
    BomSourceCodeManager,
    BranchSourceCodeManager,
    GcbCommandFactory,
    GradleCommandProcessor,

    check_options_set,
    check_subprocesses_to_logfile,
    raise_and_log_error,
    ConfigError)


NON_DEBIAN_BOM_REPOSITORIES = ['spin']


class BuildDebianCommand(GradleCommandProcessor):
  def __init__(self, factory, options, **kwargs):
    options.github_disable_upstream_push = True
    super(BuildDebianCommand, self).__init__(factory, options, **kwargs)

  def _do_can_skip_repository(self, repository):
    if repository.name in NON_DEBIAN_BOM_REPOSITORIES:
      return True

    build_version = self.scm.get_repository_service_build_version(repository)
    return self.gradle.consider_debian_on_bintray(repository, build_version)

  def _do_repository(self, repository):
    """Implements RepositoryCommandProcessor interface."""
    options = self.options
    cloudbuild_config = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'cloudbuild', 'debs.yml')
    service_name = self.scm.repository_name_to_service_name(repository.name)
    source_info = self.scm.lookup_source_info(repository)
    substitutions = {'_BRANCH_NAME': options.git_branch,
                     '_BRANCH_TAG': re.sub(r'\W', '_', options.git_branch),
                     '_IMAGE_NAME': service_name,
                     '_BUILD_NUMBER': source_info.build_number,
                     '_VERSION': source_info.summary.version}
    # Convert it to the format expected by gcloud: "_FOO=bar,_BAZ=qux"
    substitutions_arg = ','.join('='.join((str(k), str(v))) for k, v in
                                 substitutions.items())
    command = ('gcloud builds submit '
               ' --account={account}'
               ' --project={project}'
               ' --substitutions={substitutions_arg}'
               ' --config={cloudbuild_config} .'
               .format(account=options.gcb_service_account,
                       project=options.gcb_project,
                       substitutions_arg=substitutions_arg,
                       cloudbuild_config=cloudbuild_config))

    logfile = self.get_logfile_path(repository.name + '-gcb-build')
    labels = {'repository': repository.name}
    self.metrics.time_call(
        'DebBuild', labels, self.metrics.default_determine_outcome_labels,
        check_subprocesses_to_logfile,
        repository.name + ' deb build', logfile, [command], cwd=repository.git_dir)


class BuildDebianFactory(GcbCommandFactory):
  def init_argparser(self, parser, defaults):
    """Adds command-specific arguments."""
    super(BuildDebianFactory, self).init_argparser(parser, defaults)
    self.add_argument(
        parser, 'bintray_org', defaults, None,
        help='The bintray organization for the bintray_debian_repository.')
    self.add_argument(
        parser, 'bintray_debian_repository', defaults, None,
        help='Repository in the --bintray_org where the debs are published.')
    self.add_argument(
        parser, 'skip_existing', defaults, False, type=bool,
        help='Skip builds if the desired version already exists on bintray.')

def register_commands(registry, subparsers, defaults):
  build_debian_factory = BuildDebianFactory(
      'build_debians', BuildDebianCommand,
      'Build one or more debian packages from the local git repository.',
      BomSourceCodeManager)

  build_debian_factory.register(registry, subparsers, defaults)
