# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

"""Unit tests for .asf.yaml GitHub branch protection feature."""

from types import SimpleNamespace
from typing import Any, Mapping

from asfyaml.feature.github.branch_protection import branch_protection as configure_branch_protection


def _protected_ref(name: str) -> dict[str, Any]:
    return {"name": name, "branchProtectionRule": {"pattern": name}}


def _unprotected_ref(name: str) -> dict[str, Any]:
    return {"name": name, "branchProtectionRule": None}


class FakeBranch:
    def __init__(self, name: str):
        self.name = name
        self.remove_protection_calls = 0

    def remove_protection(self) -> None:
        self.remove_protection_calls += 1


class FakeRequester:
    def __init__(self, refs: list[dict[str, Any]] | None = None):
        self.refs = refs or []
        self.graphql_calls: list[dict[str, Any]] = []

    def graphql_query(self, query: str, variables: Mapping[str, Any]):
        self.graphql_calls.append({"query": query, "variables": dict(variables)})
        data = {
            "data": {
                "repository": {
                    "refs": {
                        "nodes": self.refs,
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            }
        }
        return {}, data


class FakeFeature:
    def __init__(
        self,
        *,
        yaml: dict[str, Any],
        previous_yaml: Any,
        requester: FakeRequester,
        noop_enabled: bool = False,
    ):
        self.yaml = yaml
        self.previous_yaml = previous_yaml
        self.repository = SimpleNamespace(org_id="apache", name="infrastructure-asfyaml")
        self.branches: dict[str, FakeBranch] = {}
        self.ghrepo = SimpleNamespace(_requester=requester, get_branch=self._get_branch)
        self._noop_enabled = noop_enabled

    def _get_branch(self, branch: str) -> FakeBranch:
        return self.branches.setdefault(branch, FakeBranch(branch))

    def noop(self, directive: str) -> bool:
        if self._noop_enabled:
            print(f"[github::{directive}] Not applying changes, noop mode active.")
            return True
        return False


def test_branch_protection_removed_section_clears_previously_managed_protection():
    requester = FakeRequester(
        refs=[
            _protected_ref("main"),
            _protected_ref("branch-3.x"),
            _unprotected_ref("feature/foo"),
        ]
    )
    feature = FakeFeature(
        yaml={},
        previous_yaml={"protected_branches": {"main": {}}},
        requester=requester,
    )

    configure_branch_protection(feature)

    assert len(requester.graphql_calls) == 1
    assert feature.branches["main"].remove_protection_calls == 1
    assert feature.branches["branch-3.x"].remove_protection_calls == 1
    assert "feature/foo" not in feature.branches


def test_branch_protection_absent_section_without_history_does_nothing():
    requester = FakeRequester(refs=[_protected_ref("main")])
    feature = FakeFeature(
        yaml={},
        previous_yaml={},
        requester=requester,
    )

    configure_branch_protection(feature)

    assert requester.graphql_calls == []
    assert feature.branches == {}


def test_branch_protection_null_section_clears_protection():
    requester = FakeRequester(refs=[_protected_ref("main")])
    feature = FakeFeature(
        yaml={"protected_branches": None},
        previous_yaml={},
        requester=requester,
    )

    configure_branch_protection(feature)

    assert len(requester.graphql_calls) == 1
    assert feature.branches["main"].remove_protection_calls == 1


def test_branch_protection_removed_section_noop_mode_does_not_remove_protection():
    requester = FakeRequester(refs=[_protected_ref("main")])
    feature = FakeFeature(
        yaml={},
        previous_yaml={"protected_branches": {"main": {}}},
        requester=requester,
        noop_enabled=True,
    )

    configure_branch_protection(feature)

    assert len(requester.graphql_calls) == 1
    assert feature.branches["main"].remove_protection_calls == 0


def test_branch_protection_non_dict_previous_yaml_treated_as_empty():
    requester = FakeRequester(refs=[_protected_ref("main")])
    feature = FakeFeature(
        yaml={},
        previous_yaml=None,
        requester=requester,
    )

    configure_branch_protection(feature)

    assert requester.graphql_calls == []
    assert feature.branches == {}
