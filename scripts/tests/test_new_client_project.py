"""Tests for scripts/new_client_project.py on a synthetic base plan.

The real GoldberryGrove_BasePlan.qgz lives outside the repo (Permaculture
Plans/Layouts/), so the fixture below is a reduced QGIS 3.x project with the
same element shapes: nested layer-tree groups, projectlayers, the legacy
<legend>, layerorder, custom-order, snapping, a visibility preset and a print
layout whose map item lists layers. Three home-farm layers, one XYZ basemap.
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import new_client_project as ncp  # noqa: E402

BASE_QGS = """<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis projectname="Goldberry Grove base plan" version="3.34.9-Prizren" saveUser="josh">
  <homePath path=""/>
  <title>Goldberry Grove base plan</title>
  <projectCrs><spatialrefsys><authid>EPSG:26917</authid></spatialrefsys></projectCrs>
  <layer-tree-group>
    <customproperties><Option/></customproperties>
    <layer-tree-group name="Basemaps" expanded="1" checked="Qt::Checked">
      <layer-tree-layer id="OSM_xyz_1" name="OpenStreetMap" providerKey="wms" checked="Qt::Checked" expanded="0" source="type=xyz&amp;url=https://tile.openstreetmap.org/%7Bz%7D/%7Bx%7D/%7By%7D.png">
        <customproperties><Option/></customproperties>
      </layer-tree-layer>
    </layer-tree-group>
    <layer-tree-group name="Terrain" expanded="1" checked="Qt::Checked">
      <layer-tree-layer id="ClippedDEM_a1" name="ClippedDEM" providerKey="gdal" checked="Qt::Checked" expanded="1" source="./ClippedDEM.tif"/>
      <layer-tree-layer id="Contours10ft_b2" name="Contours 10ft" providerKey="ogr" checked="Qt::Checked" expanded="1" source="./contours.shp"/>
    </layer-tree-group>
    <layer-tree-group name="Water" expanded="1" checked="Qt::Checked">
      <layer-tree-group name="Ponds" expanded="1" checked="Qt::Checked">
        <layer-tree-layer id="Ponds_c3" name="Ponds" providerKey="ogr" checked="Qt::Checked" expanded="1" source="./ponds.shp"/>
      </layer-tree-group>
    </layer-tree-group>
    <layer-tree-group name="Planning" expanded="1" checked="Qt::Checked"/>
    <custom-order enabled="0">
      <item>OSM_xyz_1</item>
      <item>ClippedDEM_a1</item>
      <item>Contours10ft_b2</item>
      <item>Ponds_c3</item>
    </custom-order>
  </layer-tree-group>
  <snapping-settings enabled="0">
    <individual-layer-settings>
      <layer-setting id="Contours10ft_b2" enabled="1"/>
      <layer-setting id="Ponds_c3" enabled="1"/>
    </individual-layer-settings>
  </snapping-settings>
  <legend updateDrawingOrder="true">
    <legendgroup name="Terrain" open="true" checked="Qt::Checked">
      <legendlayer drawingOrder="-1" open="true" checked="Qt::Checked" name="ClippedDEM" showFeatureCount="0">
        <filegroup open="true" hidden="false"><legendlayerfile isInOverview="0" layerid="ClippedDEM_a1" visible="1"/></filegroup>
      </legendlayer>
    </legendgroup>
  </legend>
  <projectlayers>
    <maplayer type="raster"><id>OSM_xyz_1</id><datasource>type=xyz&amp;url=https://tile.openstreetmap.org/{z}/{x}/{y}.png</datasource><layername>OpenStreetMap</layername><provider>wms</provider></maplayer>
    <maplayer type="raster"><id>ClippedDEM_a1</id><datasource>./ClippedDEM.tif</datasource><layername>ClippedDEM</layername><provider>gdal</provider></maplayer>
    <maplayer type="vector" geometry="Line"><id>Contours10ft_b2</id><datasource>./contours.shp</datasource><layername>Contours 10ft</layername><provider encoding="UTF-8">ogr</provider></maplayer>
    <maplayer type="vector" geometry="Polygon"><id>Ponds_c3</id><datasource>./ponds.shp</datasource><layername>Ponds</layername><provider encoding="UTF-8">ogr</provider></maplayer>
  </projectlayers>
  <layerorder>
    <layer id="OSM_xyz_1"/>
    <layer id="ClippedDEM_a1"/>
    <layer id="Contours10ft_b2"/>
    <layer id="Ponds_c3"/>
  </layerorder>
  <visibility-presets>
    <visibility-preset name="Hydrology" has-expanded-info="1">
      <layer id="OSM_xyz_1" visible="1"/>
      <layer id="Ponds_c3" visible="1"/>
    </visibility-preset>
  </visibility-presets>
  <projectMetadata><title>Goldberry Grove base plan</title></projectMetadata>
  <Layouts>
    <Layout name="Site plan A3" units="mm">
      <LayoutItem type="65639" id="map">
        <LayerSet>
          <Layer provider="wms" name="OpenStreetMap">OSM_xyz_1</Layer>
          <Layer provider="ogr" name="Ponds">Ponds_c3</Layer>
        </LayerSet>
      </LayoutItem>
    </Layout>
  </Layouts>
</qgis>
"""

HOME_IDS = {"ClippedDEM_a1", "Contours10ft_b2", "Ponds_c3"}


@pytest.fixture
def base_qgz(tmp_path: Path) -> Path:
    p = tmp_path / "GoldberryGrove_BasePlan.qgz"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("GoldberryGrove_BasePlan.qgs", BASE_QGS)
        zf.writestr("GoldberryGrove_BasePlan.qgd", b"SQLite format 3\x00")
    return p


def _ids_referenced(xml: bytes) -> set[str]:
    """Every layer id mentioned anywhere in the project, by any mechanism."""
    root = ET.fromstring(xml.split(b"<qgis", 1)[1].join([b"<qgis", b""]))
    found: set[str] = set()
    for el in root.iter():
        for attr in ("id", "layerid"):
            v = el.get(attr)
            if v and (v in HOME_IDS or v == "OSM_xyz_1"):
                found.add(v)
        if el.tag in {"item", "Layer", "id"} and (el.text or "").strip():
            found.add(el.text.strip())
    return found


def test_slugify_keeps_lead_id_and_lowercases():
    assert ncp.slugify("142 Smith Hollow") == "142-smith-hollow"
    assert ncp.slugify("  Smith & Sons / Ridge (WV) ") == "smith-sons-ridge-wv"
    with pytest.raises(ValueError):
        ncp.slugify("///")


def test_inventory_lists_groups_in_tree_order_and_layers_with_paths():
    root = ET.fromstring(BASE_QGS.split("\n", 1)[1])
    groups, layers = ncp.inventory(root)
    assert groups == ["Basemaps", "Terrain", "Water", "Ponds", "Planning"]
    by_name = {lay.name: lay for lay in layers}
    assert by_name["Ponds"].group_path == ("Water", "Ponds")
    assert by_name["OpenStreetMap"].is_basemap and by_name["OpenStreetMap"].provider == "wms"
    assert not by_name["Contours 10ft"].is_basemap


def test_home_farm_layers_removed_everywhere_groups_and_basemap_kept(base_qgz: Path):
    _, xml = ncp.read_qgs(base_qgz)
    out, report = ncp.build_client_project(xml, "142 Smith Hollow")

    assert report.slug == "142-smith-hollow"
    assert report.groups == ["Basemaps", "Terrain", "Water", "Ponds", "Planning"]
    assert {lay.id for lay in report.removed} == HOME_IDS
    assert [lay.id for lay in report.kept] == ["OSM_xyz_1"]

    # no stray references to any removed layer, by any mechanism
    assert _ids_referenced(out) == {"OSM_xyz_1"}
    assert out.startswith(b"<!DOCTYPE qgis")  # prolog preserved

    root = ET.fromstring(out.split(b"\n", 1)[1])
    # all groups survive, including the now-empty ones and the nested one
    names = [g.get("name") for g in root.iter("layer-tree-group") if g.get("name")]
    assert names == ["Basemaps", "Terrain", "Water", "Ponds", "Planning"]
    # the layout map item still lists the basemap, not the ponds
    assert [l.text for l in root.iterfind(".//LayerSet/Layer")] == ["OSM_xyz_1"]
    # legacy legend: the Terrain legendgroup remains, its legendlayer is gone
    assert root.find(".//legendgroup[@name='Terrain']") is not None
    assert root.find(".//legendlayer") is None
    # retitled in all three places
    assert root.get("projectname") == "142 Smith Hollow"
    assert root.findtext("title") == "142 Smith Hollow"
    assert root.findtext("./projectMetadata/title") == "142 Smith Hollow"
    # CRS untouched
    assert root.findtext("./projectCrs/spatialrefsys/authid") == "EPSG:26917"


def test_keep_glob_retains_matching_home_layer(base_qgz: Path):
    _, xml = ncp.read_qgs(base_qgz)
    out, report = ncp.build_client_project(xml, "142 Smith Hollow", keep=["Contours*"])
    assert {lay.name for lay in report.kept} == {"OpenStreetMap", "Contours 10ft"}
    assert _ids_referenced(out) == {"OSM_xyz_1", "Contours10ft_b2"}
    # snapping entry for the kept layer survives, the ponds one is gone
    root = ET.fromstring(out.split(b"\n", 1)[1])
    assert [s.get("id") for s in root.iterfind(".//layer-setting")] == ["Contours10ft_b2"]


def test_no_basemaps_drops_everything(base_qgz: Path):
    _, xml = ncp.read_qgs(base_qgz)
    out, report = ncp.build_client_project(xml, "7 Bare", keep_basemaps=False)
    assert report.kept == []
    assert _ids_referenced(out) == set()
    assert ET.fromstring(out.split(b"\n", 1)[1]).find("./projectlayers/maplayer") is None


def test_cli_writes_named_qgz_without_qgd_and_refuses_overwrite(base_qgz: Path, tmp_path: Path, capsys):
    out_dir = tmp_path / "clients"
    rc = ncp.main(["--base", str(base_qgz), "--opportunity", "142 Smith Hollow", "--out-dir", str(out_dir)])
    assert rc == 0
    target = out_dir / "142-smith-hollow.qgz"
    assert target.is_file()
    with zipfile.ZipFile(target) as zf:
        assert zf.namelist() == ["142-smith-hollow.qgs"]  # inner .qgs renamed, no .qgd copied
        inner = zf.read("142-smith-hollow.qgs")
    assert _ids_referenced(inner) == {"OSM_xyz_1"}
    assert "layers removed (3)" in capsys.readouterr().out

    # second run without --force must not clobber
    assert ncp.main(["--base", str(base_qgz), "--opportunity", "142 Smith Hollow", "--out-dir", str(out_dir)]) == 1
    assert "exists" in capsys.readouterr().err
    assert ncp.main(["--base", str(base_qgz), "--opportunity", "142 Smith Hollow", "--out-dir", str(out_dir), "--force"]) == 0


def test_cli_list_and_dry_run_write_nothing(base_qgz: Path, tmp_path: Path, capsys):
    assert ncp.main(["--base", str(base_qgz), "--list"]) == 0
    out = capsys.readouterr().out
    assert "5 groups, 4 layers" in out and "(basemap)" in out
    assert ncp.main(["--base", str(base_qgz), "--opportunity", "9 Dry", "--out-dir", str(tmp_path / "x"), "--dry-run"]) == 0
    assert "dry run: would write" in capsys.readouterr().out
    assert not (tmp_path / "x").exists()


def test_missing_base_is_exit_2(tmp_path: Path):
    assert ncp.main(["--base", str(tmp_path / "nope.qgz"), "--opportunity", "1 x"]) == 2
