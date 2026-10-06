"""Check publisher-page discovery without downloading approval records."""

import html
import json

import pytest
import requests

from pipelines.extract.sba_resources import (
    fetch_sba_package_metadata,
    resolve_sba_resources,
)
from pipelines.utils.source_config_models import (
    DEFAULT_SBA_PACKAGE_URL,
    load_sba_resources_config,
)
from tests.unit.extract_test_helpers import sample_sba_package_metadata


def _page_session(monkeypatch, body, status_code=200):
    response = requests.Response()
    response.status_code = status_code
    response.headers["Content-Type"] = "text/html; charset=utf-8"
    response.encoding = "utf-8"
    response._content = body.encode("utf-8")
    session = requests.Session()
    monkeypatch.setattr(session, "get", lambda *args, **kwargs: response)
    return session


def test_dataset_page_resolves_all_configured_resources_and_caches_links(
    monkeypatch, tmp_path
):
    resources = sample_sba_package_metadata()["resources"]
    resources[0]["name"] = "7(a) and 504 FOIA Data Dictionary (xlsx)"
    anchors = []
    for resource in resources:
        filename = resource["url"].rsplit("/", 1)[-1]
        anchors.append(
            f'<a href="/files/{filename}" class="extra distribution-link" '
            f'data-format="{resource["format"]}"><span>{html.escape(resource["name"])}</span></a>'
        )
    anchors.append('<a href="/unrelated.csv">FOIA 7(a) FY2020 Present</a>')
    session = _page_session(monkeypatch, "<html>" + "".join(anchors) + "</html>")
    cache_path = tmp_path / "metadata.json"
    metadata = fetch_sba_package_metadata(session=session, cache_path=cache_path)
    specs = load_sba_resources_config().resources
    resolved = resolve_sba_resources(specs, metadata)
    assert set(resolved) == {spec.logical_name for spec in specs}
    assert resolved["sba_foia_data_dictionary"].title == resources[0]["name"]
    assert (
        resolved["sba_7a_fy2020_present"].url
        == "https://data.sba.gov/files/7a_2020_present.csv"
    )
    assert metadata["source_url"] == DEFAULT_SBA_PACKAGE_URL
    assert len(metadata["resources"]) == 7
    assert json.loads(cache_path.read_text()) == metadata


@pytest.mark.parametrize(
    "status_code,error", [(200, ValueError), (404, requests.HTTPError)]
)
def test_dataset_discovery_rejects_error_or_unrecognized_page(
    monkeypatch, tmp_path, status_code, error
):
    session = _page_session(
        monkeypatch, "<html>Publisher error page</html>", status_code
    )
    cache_path = tmp_path / "metadata.json"
    with pytest.raises(error):
        fetch_sba_package_metadata(session=session, cache_path=cache_path)
    assert not cache_path.exists()
