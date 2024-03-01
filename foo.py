from pyray import *
from raylib import ffi

SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480


def main():
    init_window(SCREEN_WIDTH, SCREEN_HEIGHT, "Foo")
    set_exit_key(KeyboardKey.KEY_ESCAPE)
    set_target_fps(30)


    # This works
    # https://github.com/electronstudio/raylib-python-cffi
    flag = ffi.new("bool *", True)

    while not window_should_close():
        begin_drawing()
        clear_background(WHITE)

        gui_check_box(Rectangle(40, 40, 100, 100), "Just a checkbox", flag)

        end_drawing()


main()
