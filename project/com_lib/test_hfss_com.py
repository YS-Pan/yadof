from __future__ import annotations

import json

import numpy as np

from project.com_lib import hfss_com


def test_export_writes_only_canonical_metadata_array(tmp_path):
    class FakeSolutionData:
        primary_sweep = "Freq"
        intrinsics = {"Freq": ["2.40GHz", "2.48GHz"]}
        units_sweeps = {"Freq": "GHz"}

        @staticmethod
        def data_real(_expression):
            return np.asarray([-12.0, -10.0], dtype=float)

    class FakePost:
        @staticmethod
        def get_solution_data(**_kwargs):
            return FakeSolutionData()

    class FakeHfss:
        post = FakePost()

    path = hfss_com.save_modal(
        FakeHfss(),
        "dB(S(1,1))",
        setup="Setup1 : Sweep",
        out_dir=str(tmp_path),
        output_name="s11_test",
    )

    with np.load(path, allow_pickle=False) as data:
        assert "metadata" in data.files
        assert "meta" not in data.files
        metadata = json.loads(str(data["metadata"].item()))

    assert metadata["rawdata_name"] == "s11_test"
    assert metadata["shape"] == [2]
