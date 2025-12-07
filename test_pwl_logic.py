import unittest
import unittest.mock
import tkinter as tk
import customtkinter as ctk
from pwl_editor import PWLEditor

class TestPWLEditorLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create a hidden root window
        cls.root = ctk.CTk()
        cls.root.withdraw()
        cls.app = PWLEditor(cls.root)
    
    @classmethod
    def tearDownClass(cls):
        # Clean up 'after' callbacks to avoid "invalid command name" errors
        try:
            for after_id in cls.root.tk.call('after', 'info'):
                cls.root.after_cancel(after_id)
        except Exception:
            pass
        try:
            cls.root.quit()
            cls.root.destroy()
        except Exception:
            pass

    def test_engineering_format(self):
        # Test standard prefixes
        self.assertEqual(self.app.engineering_format(1e-3), "1m")
        self.assertEqual(self.app.engineering_format(1.5e-6), "1.5u")
        self.assertEqual(self.app.engineering_format(1000), "1k")
        self.assertEqual(self.app.engineering_format(1e6), "1M")
        self.assertEqual(self.app.engineering_format(1e9), "1G")
        
        # Test zero
        self.assertEqual(self.app.engineering_format(0), "0")
        
        # Test negative numbers
        self.assertEqual(self.app.engineering_format(-1e-3), "-1m")
        
        # Test numbers without prefix (between 1 and 1000)
        self.assertEqual(self.app.engineering_format(100), "100")
        self.assertEqual(self.app.engineering_format(0.5), "500m")
        
        # Test potential precision loss
        # 0.5004 should be 500.4m to preserve precision
        self.assertEqual(self.app.engineering_format(0.5004), "500.4m") 
        
        # Test very small numbers (should fallback to scientific)
        self.assertEqual(self.app.engineering_format(1e-13), "1.000e-13")

    def test_parse_engineering_format(self):
        # Test standard parsing
        self.assertAlmostEqual(self.app.parse_engineering_format("1m"), 1e-3)
        self.assertAlmostEqual(self.app.parse_engineering_format("1.5u"), 1.5e-6)
        self.assertAlmostEqual(self.app.parse_engineering_format("1k"), 1000)
        
        # Test no prefix
        self.assertAlmostEqual(self.app.parse_engineering_format("0.1"), 0.1)
        self.assertAlmostEqual(self.app.parse_engineering_format("100"), 100)
        
        # Test invalid input
        with self.assertRaises(ValueError):
            self.app.parse_engineering_format("m") 
        with self.assertRaises(ValueError):
            self.app.parse_engineering_format("")
            
    def test_check_time_conflict(self):
        # Setup points
        self.app.points = [(0.0, 0.0), (1.0, 1.0)]
        
        # Test conflict
        self.assertTrue(self.app._check_time_conflict(0.0))
        self.assertTrue(self.app._check_time_conflict(0.0 + 1e-13)) # Within precision
        
        # Test no conflict
        self.assertFalse(self.app._check_time_conflict(0.5))
        
        # Test exclude index (simulating update)
        self.assertFalse(self.app._check_time_conflict(0.0, exclude_index=0))

    def test_zoom_logic(self):
        """Test zoom_to_all_points sets correct canvas boundaries"""
        # Set points directly
        self.app.points = [(0.0, 0.0), (1.0, 10.0), (2.0, -10.0)]
        
        # Call zoom
        self.app.zoom_to_all_points()
        
        # Expected calculations:
        # X: min=0.0, max=2.0. Range=2.0. Padding=0.1.
        # x_min = -0.1, x_max = 2.1
        # Y: min=-10.0, max=10.0. Range=20.0. Padding=2.0.
        # y_min = -12.0, y_max = 12.0
        
        self.assertAlmostEqual(self.app.canvas.x_min, -0.1, delta=0.001)
        self.assertAlmostEqual(self.app.canvas.x_max, 2.1, delta=0.001)
        self.assertAlmostEqual(self.app.canvas.y_min, -12.0, delta=0.001)
        self.assertAlmostEqual(self.app.canvas.y_max, 12.0, delta=0.001)

    def test_placement_preview(self):
        """Test placement preview update logic (fixes 'preview_line' error)"""
        self.app.placement_mode = True
        self.app.placement_data = [(0.0, 0.0), (1.0, 1.0)]
        self.app.current_cursor_pos = (0.5, 0.5)
        
        try:
            self.app._update_placement_preview((0.6, 0.6))
        except AttributeError as e:
            self.fail(f"_update_placement_preview raised AttributeError: {e}")
        except Exception as e:
            self.fail(f"_update_placement_preview raised Exception: {e}")
            
        self.assertEqual(self.app.current_cursor_pos, (0.6, 0.6))

    def test_m_key_interaction(self):
        """Test M key interaction (add point)"""
        # Reset
        self.app.points = []
        self.app.selected_indices = set()
        self.app.current_cursor_pos = (1.0, 1.0)
        
        # 1. Basic Add
        self.app._on_m_key(None)
        self.assertEqual(len(self.app.points), 1)
        self.assertEqual(self.app.points[0], (1.0, 1.0))
        
        # 2. Add with Selection (Simulate user scenario)
        # Select the point
        self.app.selected_indices = {0}
        self.app.primary_selected_index = 0
        
        # Move cursor
        self.app.current_cursor_pos = (2.0, 2.0)
        
        # Press M
        self.app._on_m_key(None)
        
        # Check result
        self.assertEqual(len(self.app.points), 2)
        self.assertIn((2.0, 2.0), self.app.points)
        
    def test_placement_preview_interaction(self):
        """Test placement preview updates"""
        self.app.placement_mode = True
        self.app.placement_data = [(0, 0), (1, 1)]
        self.app.current_cursor_pos = (5.0, 5.0)
        
        # Simulate update
        self.app._update_plot(fast_update=True)
        
        # Check canvas last draw args
        args = self.app.canvas.last_draw_args
        preview = args.get('placement_preview_line', [])
        self.assertTrue(len(preview) > 0)
        self.assertAlmostEqual(preview[0][0], 5.0)
        
        # Clean up
        self.app.placement_mode = False

    def test_default_axis_range(self):
        self.assertAlmostEqual(self.app.canvas.x_min, 0.0)
        self.assertAlmostEqual(self.app.canvas.x_max, 1e-3)

    def test_min_spacing_validation(self):
        pts = [
            (0.0, 0.0),
            (0.0, 1.0),
            (5e-13, 0.5),
            (5e-13, 0.7),
            (2e-12, 0.2)
        ]
        self.app.points = self.app._ensure_min_spacing(pts)
        times = [t for t, _ in self.app.points]
        for i in range(1, len(times)):
            self.assertGreaterEqual(times[i] - times[i-1], self.app.TIME_MIN_PRECISION - 1e-15)

    def test_negative_axis_limit_on_fit(self):
        self.app.points = [(-1.0, 0.0), (2.0, 0.0)]
        self.app.zoom_to_all_points()
        x_min = self.app.canvas.x_min
        x_max = self.app.canvas.x_max
        neg = max(0.0, -min(0.0, x_min))
        total = x_max - x_min
        frac = neg / total if total > 0 else 0
        self.assertLessEqual(frac, 0.051)
        self.assertGreater(self.app.canvas.x_max, 0.0)

    def test_quick_add_no_auto_zoom(self):
        # Record initial view
        x_min0 = self.app.canvas.x_min
        x_max0 = self.app.canvas.x_max
        self.app.points = []
        self.app.quick_add_point()
        self.assertAlmostEqual(self.app.canvas.x_min, x_min0)
        self.assertAlmostEqual(self.app.canvas.x_max, x_max0)

    def test_ps_scale_line_segments_visible(self):
        self.app.points = [(1e-12, 0.0), (2e-12, 0.0)]
        self.app.canvas.x_min = 0.0
        self.app.canvas.x_max = 5e-12
        self.app.canvas.y_min = -1.0
        self.app.canvas.y_max = 1.0
        calls = []
        orig_draw_grid = self.app.canvas.draw_grid
        self.app.canvas.draw_grid = lambda: None
        def rec(*args, **kwargs):
            calls.append(args)
        orig_create_line = self.app.canvas.create_line
        self.app.canvas.create_line = rec
        try:
            self.app._update_plot()
        finally:
            self.app.canvas.create_line = orig_create_line
            self.app.canvas.draw_grid = orig_draw_grid
        sx0, sy0 = self.app.canvas.world_to_screen(1e-12, 0.0)
        sx1, sy1 = self.app.canvas.world_to_screen(2e-12, 0.0)
        found = False
        for a in calls:
            if len(a) == 4:
                x0, y0, x1, y1 = a
                if abs(x0 - sx0) < 1 and abs(y0 - sy0) < 1 and abs(x1 - sx1) < 1 and abs(y1 - sy1) < 1:
                    found = True
                    break
        self.assertTrue(found)

    def test_wave_gen_supports_period_and_thigh(self):
        # Square wave: period and high time
        pts = self.app._wave_params_to_points(
            'square', period=1e-6, amp=1.0, offset=0.0, duration=1e-6,
            t_high=2e-7, tr=1e-8, tf=1e-8
        )
        # Expect transition to high around tr, and back around t_high+tf
        times = [t for t, _ in pts]
        self.assertTrue(any(abs(t - 2e-7) < 1e-10 for t in times))

    def test_wave_gen_triangle_trise(self):
        pts = self.app._wave_params_to_points(
            'triangle', period=1e-6, amp=1.0, offset=0.0, duration=1e-6,
            t_rise=3e-7
        )
        # Peak should be at t_rise within one cycle
        self.assertTrue(any(abs(t - 3e-7) < 1e-10 for t, v in pts if abs(v - 1.0) < 1e-6))

    def test_selection_persists_on_release(self):
        self.app.points = [(0.0, 0.0), (1.0, 1.0)]
        px, py = self.app.points[0]
        sx, sy = self.app.canvas.world_to_screen(px, py)
        self.app._handle_left_click(sx, sy, px, py)
        self.assertIn(0, self.app.selected_indices)
        class E: pass
        e = E()
        e.x, e.y = int(sx), int(sy)
        self.app._on_mouse_release(e)
        self.assertIn(0, self.app.selected_indices)

    def test_drag_min_dt_applied_on_release(self):
        # Two points with enough spacing initially
        self.app.points = [(0.0, 0.0), (2e-12, 0.0)]
        # Select and start drag first point
        px, py = self.app.points[0]
        sx, sy = self.app.canvas.world_to_screen(px, py)
        self.app._handle_left_click(sx, sy, px, py)
        # Simulate dragging by directly updating the point position
        new_t = 1.5e-12
        self.app.points[0] = (new_t, py)
        # Release -> min dt enforcement adjusts dragged point only
        class Ev: pass
        ev = Ev(); ev.x = int(sx); ev.y = int(sy)
        self.app._on_mouse_release(ev)
        self.assertAlmostEqual(self.app.points[1][0], 2e-12, delta=1e-15)
        self.assertAlmostEqual(self.app.points[0][0], 1e-12, delta=1e-15)

    def test_tree_double_click_no_edit(self):
        self.app.points = [(0.0, 0.0)]
        self.app._update_table()
        # Simulate double click; should not raise and should not modify points
        class E: pass
        e = E()
        e.x, e.y = 5, 5
        before = list(self.app.points)
        try:
            # Binding replaced by lambda no-op; directly calling original handler should be safe too
            # But we ensure no mutation occurs
            self.app._on_tree_double_click(e)
        except Exception:
            pass
        after = list(self.app.points)
        self.assertEqual(before, after)

    def test_cursor_optimization(self):
        """Test that cursor_only update calls update_cursor_only and not redraw"""
        self.app.placement_mode = True
        self.app.placement_data = [(0, 0), (1, 1)]
        self.app.current_cursor_pos = (5.0, 5.0)
        self.app.view_initialized = True # Prevent autoscale logic
        
        # Ensure method exists
        if not hasattr(self.app.canvas, 'update_cursor_only'):
            self.fail("Canvas does not have update_cursor_only method")

        # Mock canvas methods
        with unittest.mock.patch.object(self.app.canvas, 'redraw') as mock_redraw, \
             unittest.mock.patch.object(self.app.canvas, 'update_cursor_only') as mock_cursor:
            
            # Call with cursor_only=True
            self.app._update_plot(cursor_only=True)
            
            # Assertions
            mock_cursor.assert_called_once()
            mock_redraw.assert_not_called()
            
            # Verify arguments passed to cursor update
            call_args = mock_cursor.call_args[1] # kwargs
            self.assertTrue(call_args['placement_mode'])
            self.assertEqual(len(call_args['placement_preview_line']), 2)

        # Reset
        self.app.placement_mode = False


if __name__ == '__main__':
    unittest.main()
