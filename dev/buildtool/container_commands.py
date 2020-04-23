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

"""Implements container support commands for buildtool."""

import copy
import logging
import os
import re
import subprocess

from buildtool import (
  SPINNAKER_HALYARD_REPOSITORY_NAME,
  BomSourceCodeManager,
  BranchSourceCodeManager,
  GcbCommandFactory,
  RepositoryCommandProcessor,

  check_subprocess,
  check_subprocesses_to_logfile
)


class BuildContainerCommand(RepositoryCommandProcessor):
  def __init__(self, factory, options, source_repository_names=None, **kwargs):
    # Use own repository to avoid race conditions when commands are
    # running concurrently.
    options_copy = copy.copy(options)
    options_copy.github_disable_upstream_push = True
    super(BuildContainerCommand, self).__init__(
        factory, options_copy,
        source_repository_names=source_repository_names, **kwargs)

  def _do_can_skip_repository(self, repository):
    image_name = self.scm.repository_name_to_service_name(repository.name)
    version = self.scm.get_repository_service_build_version(repository)

    for variant in ('slim', 'ubuntu'):
      tag = "{version}-{variant}".format(version=version, variant=variant)
      if not self.__gcb_image_exists(image_name, tag):
        return False

    labels = {'repository': repository.name, 'artifact': 'gcr-container'}
    logging.info('Already have %s -- skipping build', image_name)
    self.metrics.inc_counter('ReuseArtifact', labels)
    return True

  def _do_repository(self, repository):
    """Implements RepositoryCommandProcessor interface."""
    scm = self.source_code_manager
    build_version = scm.get_repository_service_build_version(repository)
    self.__build_with_gcb(repository, build_version)

  def __gcb_image_exists(self, image_name, version):
    """Determine if gcb image already exists."""
    options = self.options
    command = ['gcloud', '--account', options.gcb_service_account,
               'container', 'images', 'list-tags',
               options.docker_registry + '/' + image_name,
               '--filter="%s"' % version,
               '--format=json']
    got = check_subprocess(' '.join(command), stderr=subprocess.PIPE)
    if got.strip() != '[]':
      return True
    return False

  def __build_with_gcb(self, repository, build_version):
    name = repository.name
    options = self.options

    cloudbuild_config = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'cloudbuild',
                                     'containers.yml')
    service_name = self.scm.repository_name_to_service_name(repository.name)
    substitutions = {'_BRANCH_NAME': options.git_branch,
                     '_BRANCH_TAG': re.sub(r'\W', '_', options.git_branch),
                     '_DOCKER_REGISTRY': options.docker_registry,
                     '_IMAGE_NAME': service_name,
                     'TAG_NAME': build_version}
    # Convert it to the format expected by gcloud: "_FOO=bar,_BAZ=qux"
    substitutions_arg = ','.join('='.join((str(k), str(v))) for k, v in
                                 substitutions.items())
    # Note this command assumes a cwd of git_dir
    command = ('gcloud builds submit '
               ' --account={account} '
               ' --project={project}'
               ' --substitutions={substitutions_arg},'
               ' --config={cloudbuild_config} .'
               .format(account=options.gcb_service_account,
                       project=options.gcb_project,
                       substitutions_arg=substitutions_arg,
                       cloudbuild_config=cloudbuild_config))

    logfile = self.get_logfile_path(name + '-gcb-build')
    labels = {'repository': repository.name}
    self.metrics.time_call(
        'GcrBuild', labels, self.metrics.default_determine_outcome_labels,
        check_subprocesses_to_logfile,
        name + ' container build', logfile, [command], cwd=repository.git_dir)

class BuildContainerFactory(GcbCommandFactory):
  pass

def register_commands(registry, subparsers, defaults):
  build_bom_containers_factory = BuildContainerFactory(
      'build_bom_containers', BuildContainerCommand,
      'Build one or more service containers from the local git repository.',
      BomSourceCodeManager)

  build_bom_containers_factory.register(registry, subparsers, defaults)
