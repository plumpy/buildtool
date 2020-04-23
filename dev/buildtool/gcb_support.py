# Copyright 2020 Google Inc. All Rights Reserved.
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

from buildtool import (
  BranchSourceCodeManager,
  RepositoryCommandFactory
)

class GcbCommandFactory(RepositoryCommandFactory):
  """Base class for build commands using GCB"""

  def init_argparser(self, parser, defaults):
    """Adds command-specific arguments."""
    super(GcbCommandFactory, self).init_argparser(parser, defaults)
    # We need the 'git_branch' argument for calling GCB. But build_debians and
    # build_bom_containers use the BomSourceCodeManager, so won't have it
    # defined.
    BranchSourceCodeManager.add_parser_args(parser, defaults)
    self.add_argument(
        parser, 'gcb_project', defaults, None,
        help='The GCP project ID that builds the containers when'
             ' using Google Container Builder.')
    self.add_argument(
        parser, 'gcb_service_account', defaults, None,
        help='Google Service Account when using the GCP Container Builder.')
    self.add_argument(
        parser, 'docker_registry', defaults, None,
        help='Docker registry to push the container images to.')
