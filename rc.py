import sys
from PyQt5.QtWidgets import QApplication, QWidget, QMainWindow, QLabel, QSlider
from PyQt5.QtGui import QPainter, QColor, QPen, QImage
from PyQt5.QtGui import QIcon
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import Qt, pyqtSignal
import random
from functools import lru_cache
from math import sqrt
from typing import List
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
        self.width = 100  # 2560 // 2
        self.height = 100  # 1440 - 35
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

        # Add paint widget and paint
        self.s = DoubleSlider(Qt.Horizontal, self)
        self.s.move(0, 120)
        self.s.resize(200, 30)
        self.s.setMinimum(0.01)
        self.s.setMaximum(1)
        self.s.setValue(0.096)

        def ps(value):
            self.m.pixel_size = value
            self.m.refreshImage()
            self.m.show()

        self.s.doubleValueChanged[float].connect(ps)

        self.s2 = DoubleSlider(Qt.Horizontal, self)
        self.s2.move(0, 150)
        self.s2.resize(200, 30)
        self.s2.setMinimum(0.01)
        self.s2.setMaximum(5)
        self.s2.setValue(4.214)

        def vp(value):
            self.m.vp_distance = value
            self.m.refreshImage()
            self.m.show()

        self.s2.doubleValueChanged[float].connect(vp)

        self.s3 = QSlider(Qt.Horizontal, self)
        self.s3.move(0, 180)
        self.s3.resize(200, 30)
        self.s3.setMinimum(1)
        self.s3.setMaximum(100)
        self.s3.setValue(35)

        def s2d(value):
            self.m.s_distance = value
            self.m.refreshImage()
            self.m.show()

        self.s3.valueChanged[int].connect(s2d)

        self.s4 = QSlider(Qt.Horizontal, self)
        self.s4.move(0, 210)
        self.s4.resize(200, 30)
        self.s4.setMinimum(1)
        self.s4.setValue(25)
        self.s4.setMaximum(100)

        def s2r(value):
            self.m.s_r = value
            self.m.refreshImage()
            self.m.show()

        self.s4.valueChanged[int].connect(s2r)

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


def _distance(vec1, vec2):
    (x1, y1, z1), (x2, y2, z2) = vec1, vec2

    return sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2 + (z1 - z2) ** 2)


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
        pixel_center = self._get_pixel_center(pixel)

        color, sphere_intersection = _intersect_scene(pixel_center, self.scene)

        if sphere_intersection is None:
            return (0, 0, 0)

        d = min(self.max_distance, _distance(sphere_intersection, pixel_center))

        r, g, b = color
        intensity = 1 - (d / self.max_distance)
        return (int(intensity * r), int(intensity * g), int(intensity * b))


def get_qcolor(r, g, b):
    return QColor(r, g, b)


@lru_cache(maxsize=None)
def grayscale_qcolor(g):
    return get_qcolor(g, g, g)


class PaintWidget(QLabel):
    def __init__(self, *args, **kwargs):
        self.pixel_size = 0.005
        self.vp_distance = 0.1
        self.s_distance = 30
        self.s_r = 30
        self.fog = 15

        super().__init__(*args, **kwargs)

        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setScaledContents(True)
        self.setMinimumSize(1, 1)

    def refreshImage(self):

        size = self.size()
        w = size.width()
        h = size.height()

        s1 = Sphere(
            center=(0, self.s_distance, self.s_r),
            radius=self.s_r,
            color=(255, 0, 0),
        )

        s2 = Sphere(
            center=(0, self.s_distance, 0), radius=self.s_r, color=(0, 255, 0)
        )

        s3 = Sphere(
            center=(0, self.s_distance, self.s_r),
            radius=self.s_r,
            color=(0, 0, 255),
        )

        scene = Scene([s1, s2, s3])

        print(self.pixel_size, self.vp_distance, self.s_distance, self.s_r)

        vp = ViewPort(
            (0, 0, 0), (0, self.vp_distance, 0), self.pixel_size, w, h, scene, self.fog
        )

        colors = []
        for y in range(h):
            for x in range(w):
                colors.extend(vp.get_pixel_color((x, y)))

        img = QImage(bytes(colors), w, h, QImage.Format_RGB888)

        self.setPixmap(QtGui.QPixmap.fromImage(img))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ex = App()
    sys.exit(app.exec_())
