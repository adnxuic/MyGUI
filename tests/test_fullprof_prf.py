import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from mygui.fullprof_prf import (
    FullProfPrfError,
    parse_fullprof_prf,
    parse_fullprof_prf_text,
)
from mygui.resource_limits import DEFAULT_RESOURCE_LIMITS


FIXTURE = Path(__file__).parent / "test_datas" / "XRD" / "YBCO.prf"


def prf_text(
    profile_rows,
    reflection_rows=(),
    *,
    point_count=None,
    reflection_count=None,
    header="2Theta Yobs Ycal Yobs-Ycal Backg Posr (hkl) K",
):
    profile_rows = tuple(profile_rows)
    reflection_rows = tuple(reflection_rows)
    point_count = len(profile_rows) if point_count is None else point_count
    reflection_count = len(reflection_rows) if reflection_count is None else reflection_count
    return "\n".join(
        (
            "Demo Chi2: 2.5 CELL: 1 2 3 90 90 120 SPGR: P 1 TEMP: 25",
            f"1 {point_count} 1.54056 1.54439 0 0 0 0",
            f"{reflection_count} 0 0",
            header,
            *profile_rows,
            *reflection_rows,
        )
    )


class FullProfPrfParserTests(unittest.TestCase):
    def test_representative_fixture_metadata_profile_and_reflections(self):
        result = parse_fullprof_prf(FIXTURE)

        self.assertEqual(result.source_name, "YBCO")
        self.assertEqual(result.metadata.title, "YBCO")
        self.assertEqual(result.metadata.chi2, 2.3177)
        self.assertEqual(
            result.metadata.cell,
            (3.88664, 3.88741, 11.66453, 90.0, 90.0, 90.0),
        )
        self.assertEqual(result.metadata.space_group, "P m m m")
        self.assertEqual(result.metadata.temperature, 0.0)
        self.assertEqual(result.metadata.wavelengths, (1.54056, 1.54439))
        self.assertEqual(len(result.profile.two_theta), 3803)
        self.assertEqual(len(result.reflections), 338)
        self.assertEqual(result.profile.two_theta[0], 10.1442)
        self.assertEqual(result.profile.prf_difference[0], -5625.2)
        self.assertAlmostEqual(result.profile.residual[0], 1599.0 - 1567.4)
        self.assertNotEqual(
            result.profile.prf_difference[0],
            result.profile.residual[0],
        )

    def test_duplicate_and_kalpha_near_positions_are_preserved_in_order(self):
        result = parse_fullprof_prf(FIXTURE)
        positions = [item.position for item in result.reflections]

        self.assertEqual(positions[:2], [15.1876, 15.2256])
        self.assertEqual(result.reflections[0].h, 0)
        self.assertEqual(result.reflections[0].k, 0)
        self.assertEqual(result.reflections[0].l, 2)
        duplicates = Counter(positions)
        self.assertEqual(duplicates[72.9547], 2)
        self.assertLess(positions.index(15.1876), positions.index(15.2256))

    def test_malformed_profile_line_is_not_dropped_and_reports_line(self):
        text = prf_text(("10 5 broken -99 1",))

        with self.assertRaisesRegex(
            FullProfPrfError,
            r"PRF line 5: profile column 3 must be numeric.*broken",
        ):
            parse_fullprof_prf_text(text)

    def test_malformed_hkl_reports_reflection_line(self):
        text = prf_text(
            ("10 5 3 -99 1",),
            ("15.2 0 ( 0 x 2 )",),
        )

        with self.assertRaisesRegex(
            FullProfPrfError,
            r"PRF line 6: reflection row.*0 x 2",
        ):
            parse_fullprof_prf_text(text)

    def test_nan_and_inf_are_rejected_with_context(self):
        for row, expected_line in (
            ("10 nan 3 -99 1", 5),
            ("10 5 inf -99 1", 5),
        ):
            with self.subTest(row=row):
                with self.assertRaisesRegex(
                    FullProfPrfError,
                    rf"PRF line {expected_line}:.*finite",
                ):
                    parse_fullprof_prf_text(prf_text((row,)))

        with self.assertRaisesRegex(FullProfPrfError, r"PRF line 6: reflection"):
            parse_fullprof_prf_text(prf_text(("10 5 3 -99 1",), ("inf 0 ( 0 0 2 )",)))

    def test_missing_header_and_empty_profile_are_rejected(self):
        with self.assertRaisesRegex(FullProfPrfError, "profile header is missing"):
            parse_fullprof_prf_text("Demo\n1 1 1.54 1.54\n0 0 0\n10 5 3 2 1")

        with self.assertRaisesRegex(FullProfPrfError, "profile contains no points"):
            parse_fullprof_prf_text(prf_text((), point_count=0))

    def test_declared_counts_and_resource_budgets_are_enforced(self):
        with self.assertRaisesRegex(FullProfPrfError, "declared point count 2"):
            parse_fullprof_prf_text(prf_text(("10 5 3 -99 1",), point_count=2))

        point_limits = replace(DEFAULT_RESOURCE_LIMITS, max_prf_points=1)
        with self.assertRaisesRegex(FullProfPrfError, "profile-point budget"):
            parse_fullprof_prf_text(
                prf_text(("10 5 3 -99 1", "11 6 4 -98 1")),
                limits=point_limits,
            )

        byte_limits = replace(DEFAULT_RESOURCE_LIMITS, max_prf_bytes=16)
        with self.assertRaisesRegex(FullProfPrfError, "byte budget"):
            parse_fullprof_prf_text(
                prf_text(("10 5 3 -99 1",)),
                limits=byte_limits,
            )

    def test_wrong_suffix_is_rejected_before_read(self):
        with self.assertRaisesRegex(FullProfPrfError, "Only FullProf .prf"):
            parse_fullprof_prf(FIXTURE.with_suffix(".txt"))


if __name__ == "__main__":
    unittest.main()
