import os
import shutil
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from nyl.secrets.sops import SopsFile
from nyl.tools.di import DependenciesProvider


@pytest.fixture
def provider() -> SopsFile:
    provider = SopsFile(Path("sops.yaml"))
    provider._cache = {"a": 1, "b": {"c": 2}, "d": [3, 4]}
    return provider


def test_SopsFile_keys(provider: SopsFile) -> None:
    assert list(provider.keys()) == ["a", "b", "b.c", "d"]


def test_SopsFile_get(provider: SopsFile) -> None:
    assert provider.get("a") == 1
    assert provider.get("b") == {"c": 2}
    assert provider.get("b.c") == 2
    assert provider.get("d") == [3, 4]
    with pytest.raises(KeyError):
        assert provider.get("e")


@pytest.mark.skipif(condition=shutil.which("sops") is None, reason="sops not installed")
def test_SopsFile_load() -> None:
    age_public_key = "age1xwtf4shhvhc0pgkcjzzp66y6fwqdpqkakl8q99gstnw7r4h0ldwswdjuz7"  # noqa
    age_secret_key = "AGE-SECRET-KEY-138R87A90CC2RKTJF2HZPNUCEKUAYKUKJVULNW2WQN25XRAS89LQS45MU4Q"
    sops_encrypted = """
a: ENC[AES256_GCM,data:0g==,iv:zBew+8J5q9Fn/GLz3OJAdYu0OFzayxjNVQ+OdVdiga4=,tag:Th86jJ6GqzB7drzfyq28+w==,type:int]
b:
    c: ENC[AES256_GCM,data:gg==,iv:5q7LH02MTKvCbD+ppWTQ67UFDoR6UCRf3o3MHOL/y20=,tag:ibpsZQVDJRFJHiwBGMU02g==,type:int]
d:
    - ENC[AES256_GCM,data:KA==,iv:4/48zJkBZTTV+cuWEqPIXgiNpui8t0UGkQ2jHy0sGSs=,tag:Acf+GbiqZxYmvPToDORTrQ==,type:int]
    - ENC[AES256_GCM,data:WQ==,iv:ojcVnttjIwemWv2O7naHAMyIskpcLkTZ/RtKKXpmBe0=,tag:On6vpcfwMW7lja5IYaCjhw==,type:int]
sops:
    kms: []
    gcp_kms: []
    azure_kv: []
    hc_vault: []
    age:
        - recipient: age1xwtf4shhvhc0pgkcjzzp66y6fwqdpqkakl8q99gstnw7r4h0ldwswdjuz7
          enc: |
            -----BEGIN AGE ENCRYPTED FILE-----
            YWdlLWVuY3J5cHRpb24ub3JnL3YxCi0+IFgyNTUxOSA3bFJEWFE3QjhrOUJFYzBu
            OHNZRzJXK0ZFN3oxUjFhVGFkNHlaYTdINFY0Ckw5TEVlTHc0ZExPNmNQQ214cGZl
            OWZWc2VoRE5CbXo0YzVFa0JRYWJiV1EKLS0tIEtYTVIrMXR2RFlGZVdNQkpZRVVa
            N0Fyc24yZVNraEhFaVRGOTF6VzNGNVUKOOuZRJ546pFP6WBeHapOxTwzHKgFNdeB
            KkPdoPWOuPfB7ER5r1tGTuwE6si+izKqNGYuDyGjs/fZ50V7kvfc/w==
            -----END AGE ENCRYPTED FILE-----
    lastmodified: "2024-07-09T22:26:18Z"
    mac: ENC[AES256_GCM,data:+x9JhaZ6Ga7pj4io0QPG1RhjK/vq+tkP/w9NJSyt5RSdMNajKrQOyHMWbg4yvd3g4BGSy/KfjLzCRSjOlkb15jGYx2iz/3MT50yWm139OZbpl4/1rqPL3bulFR/yyWmH/2+IP4KDclMktq/uLLCp8pEIMNdEH34WC7TLf4Cfg8o=,iv:VHhZyyIxihUNl36SyEPi+yXRD4pwvnihXqGcMfufc2E=,tag:pbiMACF7B0KL5rnOL/9Ixg==,type:str]
    pgp: []
    unencrypted_suffix: _unencrypted
    version: 3.8.1"""

    with TemporaryDirectory() as tmp, unittest.mock.patch.dict(os.environ, {"SOPS_AGE_KEY": age_secret_key}):
        sops_file = Path(tmp) / "sops.yaml"
        sops_file.write_text(sops_encrypted)

        provider = SopsFile(Path("sops.yaml"))
        provider.init(config_file=Path(tmp) / "nyl-secrets.yaml", dependencies=DependenciesProvider.default())

        assert provider.load() == {"a": 1, "b": {"c": 2}, "d": [3, 4]}
