import unittest

import numpy as np

from code.database.py_database import PyDatabase, databases


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        PyDatabase.clear()

    def tearDown(self):
        PyDatabase.clear()

    def test_update_and_get_data(self):
        db = PyDatabase()
        PyDatabase.register_sheet("Table1", "Sheet1", db)

        db.update_data(1, np.array([1.0, 2.0]))

        np.testing.assert_allclose(PyDatabase.get_data("Table1/Sheet1/1"), np.array([1.0, 2.0]))
        self.assertTrue(PyDatabase.has_data("Table1/Sheet1/1"))

    def test_update_notifies_registered_callback(self):
        db = PyDatabase()
        PyDatabase.register_sheet("Table1", "Sheet1", db)
        db.update_data(1, np.array([1.0, 2.0]))
        observed = []

        PyDatabase.data_connect("Table1/Sheet1/1", 10, "x", lambda data: observed.append(data.copy()))
        db.update_data(1, np.array([3.0, 4.0]))

        self.assertEqual(len(observed), 1)
        np.testing.assert_allclose(observed[0], np.array([3.0, 4.0]))

    def test_change_data_connection_moves_callback(self):
        db = PyDatabase()
        PyDatabase.register_sheet("Table1", "Sheet1", db)
        db.update_data(1, np.array([1.0]))
        db.update_data(2, np.array([2.0]))

        callback = lambda data: None
        PyDatabase.data_connect("Table1/Sheet1/1", 20, "x", callback)

        changed = PyDatabase.change_data_connection("Table1/Sheet1/1", "Table1/Sheet1/2", 20, "x")

        self.assertTrue(changed)
        self.assertNotIn(20, db.data["1"][1])
        self.assertIs(db.data["2"][1][20]["x"], callback)

    def test_unregister_sheet_removes_data_path(self):
        db = PyDatabase()
        PyDatabase.register_sheet("Table1", "Sheet1", db)
        db.update_data(1, np.array([1.0]))

        PyDatabase.unregister_sheet("Table1", "Sheet1")

        self.assertEqual(databases["Table1"], {})
        self.assertFalse(PyDatabase.has_data("Table1/Sheet1/1"))


if __name__ == "__main__":
    unittest.main()
