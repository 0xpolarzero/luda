import subprocess
import unittest
from unittest.mock import Mock, patch
from luda.cursor import Cursor


class CursorTests(unittest.TestCase):
    def test_invalid_coordinates_do_not_start_helper(self):
        cursor = Cursor()
        with patch('luda.cursor.subprocess.Popen') as start:
            for value in (True, 1.5, -32769, 32768):
                cursor.show(value, 0)
            start.assert_not_called()

    def test_missing_helper_is_best_effort(self):
        with patch('luda.cursor.subprocess.Popen', side_effect=OSError):
            cursor = Cursor()
            cursor.show(10, 20)
            self.assertIsNone(cursor.window_id)
            cursor.hide()
            cursor.close()

    def test_failed_start_and_close_are_bounded(self):
        process = Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired('helper', .2),
                                    subprocess.TimeoutExpired('helper', .2), 0]
        with patch('luda.cursor.subprocess.Popen', return_value=process), patch('luda.cursor.select.select',return_value=([],[],[])):
            cursor = Cursor(environment={'DISPLAY': ':555'})
            cursor.show(10,20)
            process.terminate.assert_called_once()
            process.kill.assert_called_once()
            self.assertIsNone(cursor.window_id)
            self.assertIsNone(cursor._process)

    def test_hide_failure_reaps_helper(self):
        cursor = Cursor()
        cursor._process = process = Mock()
        with patch.object(cursor,'_send'), patch('luda.cursor.select.select',return_value=([],[],[])):
            cursor.hide()
        process.wait.assert_called_once_with(timeout=.2)
        self.assertIsNone(cursor._process)


if __name__ == '__main__':
    unittest.main()
