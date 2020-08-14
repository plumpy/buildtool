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
from threading import Semaphore

from buildtool import (
    BomSourceCodeManager,
    BranchSourceCodeManager,
    GradleCommandProcessor,
    GradleCommandFactory,

    check_options_set,
    check_subprocesses_to_logfile,
    raise_and_log_error,
    ConfigError)


NON_DEBIAN_BOM_REPOSITORIES = ['spin']


class BuildDebianCommand(GradleCommandProcessor):
  def __init__(self, factory, options, **kwargs):
    options.github_disable_upstream_push = True
    super(BuildDebianCommand, self).__init__(factory, options, **kwargs)
    self.__semaphore = Semaphore(options.max_local_builds)

    if not os.environ.get('BINTRAY_KEY'):
      raise_and_log_error(ConfigError('Expected BINTRAY_KEY set.'))
    if not os.environ.get('BINTRAY_USER'):
      raise_and_log_error(ConfigError('Expected BINTRAY_USER set.'))
    check_options_set(
        options, ['bintray_org', 'bintray_jar_repository',
                  'bintray_debian_repository', 'bintray_publish_wait_secs'])

  def _do_can_skip_repository(self, repository):
    if repository.name in NON_DEBIAN_BOM_REPOSITORIES:
      return True

    build_version = self.scm.get_repository_service_build_version(repository)
    return self.gradle.consider_debian_on_bintray(repository, build_version)

  def _do_repository(self, repository):
    """Implements RepositoryCommandProcessor interface."""
    options = self.options
    name = repository.name
    args = self.gradle.get_common_args()
    cloudbuild_config = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'cloudbuild', 'debs.yml')
    service_name = self.scm.repository_name_to_service_name(repository.name)
    source_info = self.scm.lookup_source_info(repository)
    substitutions = {'_BRANCH_NAME': options.git_branch,
                     '_BRANCH_TAG': re.sub(r'\W', '_', options.git_branch),
                     '_IMAGE_NAME': service_name,
                     '_BUILD_NUMBER': source_info.build_number,
                     '_VERSION': source_info.summary.version,
                     '_DOCKER_REGISTRY': options.docker_registry}
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


class BuildDebianFactory(GradleCommandFactory):
  @staticmethod
  def add_bom_parser_args(parser, defaults):
    """Adds publishing arguments of interest to the BOM commands as well."""
    if hasattr(parser, 'added_debian'):
      return
    parser.added_debian = True
    GradleCommandFactory.add_bom_parser_args(parser, defaults)

  def init_argparser(self, parser, defaults):
    super(BuildDebianFactory, self).init_argparser(parser, defaults)

    self.add_bom_parser_args(parser, defaults)
    BranchSourceCodeManager.add_parser_args(parser, defaults)
    self.add_argument(
        parser, 'gcb_project', defaults, None,
        help='The GCP project ID when using the GCP Container Builder.')
    self.add_argument(
        parser, 'gcb_service_account', defaults, None,
        help='Google Service Account when using the GCP Container Builder.')
    self.add_argument(
        parser, 'docker_registry', defaults, None,
        help='Docker registry to push the container images to.')


def add_bom_parser_args(parser, defaults):
  """Adds parser arguments pertaining to publishing boms."""
  # These are implemented by the gradle factory, but conceptually
  # for debians, so are exported this way.
  BuildDebianFactory.add_bom_parser_args(parser, defaults)


def register_commands(registry, subparsers, defaults):
  build_debian_factory = BuildDebianFactory(
      'build_debians', BuildDebianCommand,
      'Build one or more debian packages from the local git repository.',
      BomSourceCodeManager)

  build_debian_factory.register(registry, subparsers, defaults)
