import unittest
from prepare_cad import stage_text


class ReviewStageTests(unittest.TestCase):
    def test_units_provenance_and_render_product(self):
        text = stage_text([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)], [7], .001, 'Z')
        self.assertIn('metersPerUnit = 0.001', text)
        self.assertIn('primvars:occ_face_index = [7]', text)
        self.assertIn('def RenderProduct "Camera"', text)
        self.assertIn('subdivisionScheme = "none"', text)

    def test_invalid_geometry_or_units_rejected(self):
        for points, triangles, ids, units in [([], [], [], 1),
                ([(0, 0, 0)], [(0, 0, 0)], [1], 1),
                ([(0, 0, 0)], [(0, 1, 2)], [1], 1),
                ([(float('nan'), 0, 0)], [(0, 0, 0)], [1], 1),
                ([(0, 0, 0)], [(0, 0, 0)], [1], -1)]:
            with self.assertRaises(ValueError):
                stage_text(points, triangles, ids, units, 'Z')


if __name__ == '__main__':
    unittest.main()
