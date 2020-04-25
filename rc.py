import sys
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QLabel, QSlider
from PyQt5.QtGui import QPainter, QColor, QPen, QImage
from PyQt5.QtGui import QIcon
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt, pyqtSignal
import random
from functools import lru_cache
from math import sqrt, cos, sin, pi
from typing import List
import itertools
from multiprocessing import Pool
from functools import partial
import tqdm


class DoubleSlider(QSlider):
    # create our our signal that we can connect to if necessary
    doubleValueChanged = pyqtSignal(float)

    def __init__(self, *args, decimals=3, **kargs):
        super().__init__(*args, **kargs)
        self._multi = 10 ** decimals

        self.valueChanged.connect(self.emitDoubleValueChanged)

    def emitDoubleValueChanged(self):
        value = float(super().value()) / self._multi
        self.doubleValueChanged.emit(value)

    def value(self):
        return float(super().value()) / self._multi

    def setMinimum(self, value):
        return super().setMinimum(value * self._multi)

    def setMaximum(self, value):
        return super().setMaximum(value * self._multi)

    def setSingleStep(self, value):
        return super().setSingleStep(value * self._multi)

    def singleStep(self):
        return float(super().singleStep()) / self._multi

    def setValue(self, value):
        super().setValue(int(value * self._multi))


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.title = "PyQt paint - pythonspot.com"
        self.left = 10
        self.top = 10
        self.width = 200  # 2560 // 2
        self.height = 200  # 1440 - 35
        self.initUI()

    def initUI(self):
        self.setWindowTitle("About")
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        # Set window background color
        self.setAutoFillBackground(True)
        p = self.palette()
        p.setColor(self.backgroundRole(), Qt.gray)
        self.setPalette(p)

        # Add paint widget and paint
        self.m = PaintWidget(self)
        self.m.move(0, 0)
        self.m.resize(self.width, self.height)

        self.s3 = QSlider(Qt.Horizontal, self)
        self.s3.move(0, 210)
        self.s3.resize(200, 30)
        self.s3.setMinimum(1)
        self.s3.setMaximum(400)
        self.s3.setValue(35)

        def sd(value):
            self.m.s_distance = value
            self.m.refreshImage()
            self.m.show()

        self.s3.valueChanged[int].connect(sd)

        self.s4 = QSlider(Qt.Horizontal, self)
        self.s4.move(0, 240)
        self.s4.resize(200, 30)
        self.s4.setMinimum(1)
        self.s4.setValue(25)
        self.s4.setMaximum(100)

        def sr(value):
            self.m.s_r = value
            self.m.refreshImage()
            self.m.show()

        self.s4.valueChanged[int].connect(sr)

        self.s5 = QSlider(Qt.Horizontal, self)
        self.s5.move(0, 270)
        self.s5.resize(200, 30)
        self.s5.setMinimum(1)
        self.s5.setValue(25)
        self.s5.setMaximum(500)

        def sf(value):
            self.m.fog = value
            self.m.refreshImage()
            self.m.show()

        self.s5.valueChanged[int].connect(sf)

        self.s6 = QSlider(Qt.Horizontal, self)
        self.s6.move(0, 300)
        self.s6.resize(200, 30)
        self.s6.setMinimum(0)
        self.s6.setValue(25)
        self.s6.setMaximum(360)

        def sr(value):
            self.m.rot = value
            self.m.refreshImage()
            self.m.show()

        self.s6.valueChanged[int].connect(sr)

        self.show()


class Sphere:
    def __init__(self, center, radius, color):
        self.center = center
        self.radius = radius
        self.color = color


class Scene:
    def __init__(self, spheres):
        self.spheres = spheres


def _intersect_sphere(vec, sphere: Sphere):
    a, b, c = vec
    (s1, s2, s3), r = sphere.center, sphere.radius

    qa = a * a + b * b + c * c
    qb = -2 * (s1 * a + s2 * b + s3 * c)
    qc = s1 * s1 + s2 * s2 + s3 * s3 - r * r

    det = qb * qb - 4 * qa * qc

    # No intersections with the sphere
    if det < 0:
        return None

    denom = 2 * qa

    right = sqrt(det) / denom
    left = -qb / denom

    # Remove spheres that are behind the viewport and get the closest one
    solutions = [solution for solution in (left - right, left + right) if solution > 1]

    # All spheres are between the camera and the viewport
    if not solutions:
        return None

    # Only consider the closest solution
    solution = min(solutions)

    # The intersected sphere
    if solution < 1:
        return None

    return solution


def _intersect_scene(vec, scene: Scene):
    intersections = (
        (sphere.color, _intersect_sphere(vec, sphere))
        for sphere in scene.spheres
        if sphere is not None
    )

    solutions = [
        (color, factor) for color, factor in intersections if factor is not None
    ]

    if not solutions:
        return None, None

    def get_factor(solution):
        color, factor = solution
        return factor

    color, factor = min(solutions, key=get_factor)

    a, b, c = vec

    return color, (factor * a, factor * b, factor * c)


def _distance_sq(vec1, vec2):
    (x1, y1, z1), (x2, y2, z2) = vec1, vec2

    return (x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2


class ViewPort:
    def __init__(self, camera, center, pixel_size, width, height, scene, max_distance):
        self.cx, self.cy, self.cz = center
        self.pixel_size = pixel_size
        self.vpw = pixel_size * width
        self.vph = pixel_size * height
        self.scene = scene
        self.max_distance = max_distance

        # Half the width left from the center gets us the left edge of the
        # top-left pixel
        self.topleft_pixel_left = self.cx - self.vpw / 2

        # Half the height up from the center gets us the top edge of the top-left pixel
        self.topleft_pixel_top = self.cz + self.vph / 2

        self.pixel_centers = {
            (x, y): self._get_pixel_center((x, y))
            for x, y in itertools.product(range(width), range(height))
        }

    def _get_pixel_center(self, pixel):
        # Half a pixel size from the pixel's top left corner gets us to the center
        pixel_center_correction = self.pixel_size / 2

        x, y = pixel

        return (
            self.topleft_pixel_left + self.pixel_size * x + pixel_center_correction,
            self.cy,
            self.topleft_pixel_top - self.pixel_size * y - pixel_center_correction,
        )

    def get_pixel_color(self, pixel):
        pixel_center = self.pixel_centers[pixel]

        color, sphere_intersection = _intersect_scene(pixel_center, self.scene)

        if sphere_intersection is None:
            return (0, 0, 0)

        d = min(self.max_distance ** 2, _distance_sq(sphere_intersection, pixel_center))

        r, g, b = color
        intensity = 1 - (d / (self.max_distance ** 2))
        return (int(intensity * r), int(intensity * g), int(intensity * b))


p = Pool(12)


@lru_cache(maxsize=None)
def gen_viewport(*args, **kwargs):
    return ViewPort(*args, **kwargs)


def gen_image(w, h, pixel_size, vp_distance, s_distance, s_r, fog, rot):
    def to_rad(a):
        return a * 2 * pi / 360

    s1rot = to_rad(rot)
    s3rot = to_rad(rot + 180)

    s1 = Sphere(
        center=(s_r * 2 * sin(s1rot), s_distance + s_r * 2 * cos(s1rot), 0,),
        radius=s_r / 2,
        color=(255, 0, 0),
    )

    s2 = Sphere(center=(0, s_distance, 0), radius=s_r, color=(0, 255, 0))

    s3 = Sphere(
        center=(s_r * 2 * sin(s3rot), s_distance + s_r * 2 * cos(s3rot), 0,),
        radius=s_r / 2,
        color=(0, 0, 255),
    )

    scene = Scene([s1, s2, s3])

    print(f"{s_distance=} {s_r=} {fog=}")

    vp = gen_viewport((0, 0, 0), (0, vp_distance, 0), pixel_size, w, h, scene, fog)

    colors = []
    for y in range(h):
        for x in range(w):
            colors += vp.get_pixel_color((x, y))

    return colors

    # global p
    # return sum(
    #     map(vp.get_pixel_color, itertools.product(range(h), range(w))), tuple()
    # )


class PaintWidget(QLabel):
    def __init__(self, *args, **kwargs):
        self.pixel_size = 0.01
        self.vp_distance = 35
        self.s_distance = 25
        self.s_r = 25
        self.fog = 25
        self.rot = 1

        super().__init__(*args, **kwargs)

        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setScaledContents(True)
        self.setMinimumSize(1, 1)

    def refreshImage(self):
        colors = gen_image(
            self.size().width(),
            self.size().height(),
            self.pixel_size,
            self.vp_distance,
            self.s_distance,
            self.s_r,
            self.fog,
            self.rot,
        )

        img = QImage(
            bytes(colors),
            self.size().width(),
            self.size().height(),
            QImage.Format_RGB888,
        )

        self.setPixmap(QtGui.QPixmap.fromImage(img))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec_())
