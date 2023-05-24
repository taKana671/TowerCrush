import sys
from enum import Enum, auto

from direct.gui.DirectGui import OnscreenText, Plain, OnscreenImage, DirectButton
from direct.interval.IntervalGlobal import Sequence, Parallel, Func, Wait
from direct.showbase.ShowBaseGlobal import globalClock
from direct.showbase.ShowBase import ShowBase
# from panda3d.bullet import BulletSphereShape
from panda3d.bullet import BulletWorld, BulletDebugNode
from panda3d.core import PandaNode, NodePath, TextNode, TransparencyAttrib
from panda3d.core import Vec3, LColor, BitMask32, Point3, Quat

from direct.showbase.InputStateGlobal import inputState


from bubble import Bubbles
from lights import BasicAmbientLight, BasicDayLight
from scene import Scene
from tower import towers, Colors, Block


PATH_SPHERE = "models/sphere/sphere"
PATH_TEXTURE_MULTI = 'textures/multi.jpg'
PATH_TEXTURE_TWOTONE = 'textures/two_tone.jpg'
PATH_START_SCREEN = 'images/start.png'
CHECK_REPEAT = 0.2
WAIT_COUNT = 5


class Ball(Enum):

    DELETED = auto()
    READY = auto()
    MOVE = auto()


class Game(Enum):

    PLAY = auto()
    GAMEOVER = auto()
    START = auto()
    CLEAR = auto()


class ColorBall(NodePath):

    def __init__(self, bubbles, navigator):
        super().__init__(PandaNode('ball'))
        # self.reparentTo(base.render)
        self.reparent_to(navigator)

        # self.start_pos = Point3(0, -21, 0)
        self.start_pos = Point3(0, -50, 0)

        self.start_hpr = Vec3(95, 0, 30)
        self.normal_ball = NormalBall(bubbles)
        self.multi_ball = MultiColorBall(bubbles)
        self.twotone_ball = TwoToneBall(bubbles)
        self.ball = None

        self.ball_number = OnscreenText(
            style=Plain,
            pos=(-0.02, -0.98),
            align=TextNode.ACenter,
            scale=0.1,
            mayChange=True
        )

    def initialize(self, tower):
        self.tower = tower
        self.cnt = self.tower.level
        if self.ball is not None and self.ball.hasParent():
            self._delete()
        self.used = False
        self.state = None
        self.pos = self.start_pos
        self.hpr = self.start_hpr
        self.ball_number.setText('')

    def setup(self, color, camera):
        if color == 'MULTI':
            self.ball = self.multi_ball
        elif color == 'TWOTONE':
            self.used = True
            self.ball = self.twotone_ball
        else:
            self.ball = self.normal_ball
            self.ball.setColor(color)

        self.pos.z = camera.getZ() - 1.5
        self.ball.setPos(self.pos)
        # ball's initial h 95 - camera's initial h 12 = 83
        self.hpr.x = camera.getH() + 83
        self.ball.setHpr(self.hpr)
        self.ball.reparentTo(self)
        self.state = Ball.READY
        # show the number of throwing a ball.
        self.ball_number.reparentTo(base.aspect2d)
        self.ball_number.setText(str(self.cnt))

    def _delete(self):
        self.ball.detachNode()
        self.state = Ball.DELETED

    def move(self, clicked_pos, block):
        self.cnt -= 1
        self.state = Ball.MOVE
        self.ball_number.detachNode()

        Sequence(
            self.ball.posHprInterval(0.5, clicked_pos, Vec3(0, 360, 0)),
            Func(self._delete),
            Func(self.ball.hit, clicked_pos, block, self.tower)
        ).start()

    def reposition(self, rotation_angle=None, vertical_distance=None):
        if self.state == Ball.READY:
            # if rotation_angle:
            #     self.pos = self.tower.rotate(self.ball, rotation_angle)
            #     self.ball.setPos(self.pos)
            #     self.ball.setH(self.ball.getH() + rotation_angle)
            if vertical_distance:
                self.pos.z -= vertical_distance
                self.ball.setZ(self.pos.z)


class NormalBall(NodePath):

    def __init__(self, bubbles):
        super().__init__(PandaNode('normalBall'))
        ball = base.loader.loadModel(PATH_SPHERE)
        ball.reparentTo(self)
        self.setScale(0.2)
        self.bubbles = bubbles

    def hit(self, clicked_pos, block, tower):
        blocks = []
        if self.getColor() == block.getColor():
            tower.get_neighbors(block, block.getColor(), blocks)
        para = Parallel(self.bubbles.get_sequence(self.getColor(), clicked_pos))

        for block in blocks:
            pos = block.getPos()
            para.append(Sequence(
                Func(tower.clean_up, block),
                self.bubbles.get_sequence(self.getColor(), pos))
            )
        para.start()


class MultiColorBall(NodePath):

    def __init__(self, bubbles):
        super().__init__(PandaNode('multiColorBall'))
        ball = base.loader.loadModel(PATH_SPHERE)
        ball.setTexture(base.loader.loadTexture(PATH_TEXTURE_MULTI), 1)
        ball.reparentTo(self)
        self.setScale(0.2)
        self.bubbles = bubbles

    def _hit(self, color, tower):
        for block in tower.judge_colors(lambda x: x.getColor() == color):
            pos = block.getPos()
            yield Sequence(Func(tower.clean_up, block),
                           self.bubbles.get_sequence(color, pos))

    def hit(self, clicked_pos, block, tower):
        color = block.getColor()
        Parallel(
            self.bubbles.get_sequence(color, clicked_pos),
            *[seq for seq in self._hit(color, tower)]
        ).start()


class TwoToneBall(NodePath):

    def __init__(self, bubbles):
        super().__init__(PandaNode('twoToneBall'))
        ball = base.loader.loadModel(PATH_SPHERE)
        ball.setTexture(base.loader.loadTexture(PATH_TEXTURE_TWOTONE), 1)
        ball.reparentTo(self)
        self.setScale(0.2)
        self.bubbles = bubbles

    def _hit(self, color, tower):
        for block in tower.judge_colors(lambda x: x.getColor() != color):
            pos = block.getPos()
            color = block.getColor()
            yield Sequence(Func(tower.clean_up, block),
                           self.bubbles.get_sequence(color, pos))

    def hit(self, clicked_pos, block, tower):
        color = block.getColor()
        Parallel(
            self.bubbles.get_sequence(Colors.select(), clicked_pos),
            *[seq for seq in self._hit(color, tower)]
        ).start()


class TowerCrash(ShowBase):

    def __init__(self):
        super().__init__()
        self.disable_mouse()
        self.camera_lowest_z = 2.5
        self.tower_num = 0

        self.world = BulletWorld()
        self.world.set_gravity(Vec3(0, 0, -9.81))

        self.ambient_light = BasicAmbientLight()
        self.directional_light = BasicDayLight()
        self.scene = Scene(self.world)
        self.scene.reparent_to(self.render)

        self.navigator = NodePath('floater')
        self.navigator.reparent_to(self.render)
        self.camera.reparent_to(self.navigator)

        self.bubbles = Bubbles()
        self.ball = ColorBall(self.bubbles, self.navigator)
        self.gameover_seq = Sequence(Wait(3))
        self.start_screen = StartScreen(self)

        self.debug = self.render.attach_new_node(BulletDebugNode('debug'))
        self.world.set_debug_node(self.debug.node())


        self.initialize_game()

        # self.camera.set_p(-5)

        self.accept('z', self.test_move_camera, ['z', 'up'])
        self.accept('shift-z', self.test_move_camera, ['z', 'down'])
        self.accept('x', self.test_move_camera, ['x', 'up'])
        self.accept('shift-x', self.test_move_camera, ['x', 'down'])
        self.accept('y', self.test_move_camera, ['y', 'up'])
        self.accept('shift-y', self.test_move_camera, ['y', 'down'])
        self.accept('h', self.test_move_camera, ['h', 'up'])
        self.accept('shift-h', self.test_move_camera, ['h', 'down'])
        self.accept('p', self.test_move_camera, ['p', 'up'])
        self.accept('shift-p', self.test_move_camera, ['p', 'down'])
        self.accept('r', self.test_move_camera, ['r', 'up'])
        self.accept('shift-r', self.test_move_camera, ['r', 'down'])

        self.accept('escape', sys.exit)
        self.accept('d', self.toggle_debug)
        self.accept('mouse1', self.mouse_click)
        self.accept('mouse1-up', self.mouse_release)
        self.taskMgr.add(self.update, 'update')

    def test_move_camera(self, direction, move):
        if direction == 'z':
            z = self.camera.get_z()
            if move == 'up':
                self.camera.set_z(z + 2)
            elif move == 'down':
                self.camera.set_z(z - 2)

        if direction == 'y':
            y = self.camera.get_y()
            if move == 'up':
                self.camera.set_y(y + 2)
            elif move == 'down':
                self.camera.set_y(y - 2)

        if direction == 'x':
            x = self.camera.get_x()
            if move == 'up':
                self.camera.set_x(x + 2)
            elif move == 'down':
                self.camera.set_x(x - 2)

        if direction == 'h':
            h = self.camera.get_h()
            if move == 'up':
                self.camera.set_h(h + 2)
            elif move == 'down':
                self.camera.set_h(h - 2)

        if direction == 'p':
            p = self.camera.get_p()
            if move == 'up':
                self.camera.set_p(p + 2)
            elif move == 'down':
                self.camera.set_p(p - 2)

        if direction == 'r':
            r = self.camera.get_r()
            if move == 'up':
                self.camera.set_r(r + 2)
            elif move == 'down':
                self.camera.set_r(r - 2)

        # self.camera.look_at(-2, 12, 12.5)
        print(self.camera.get_pos(), self.camera.get_hpr())

    def toggle_debug(self):
        if self.debug.is_hidden():
            self.debug.show()
        else:
            self.debug.hide()

    def initialize_game(self):
        self.start_screen.reparentTo(self.aspect2d)
        self.state = None
        self.descent_distance = 0
        self.mouse_dragging = 0
        self.timer = 0
        self.click = False

        tower = towers[self.tower_num]
        # tower = towers[4]
        self.tower = tower(24, self.scene.foundation, self.world)
        # self.tower = tower(6, self.scene.foundation, self.world)
        self.tower.build()
        self.ball.initialize(self.tower)

        for _ in range(len(self.gameover_seq) - 1):
            self.gameover_seq.pop()

        # self.camera.look_at(self.floater)

        # self.camera_highest_z = (self.tower.inactive_top + 1) * self.tower.block_h
        self.camera_highest_z = self.tower.floater.get_z(self.render)

        # self.camera.set_pos(10, -40, self.camera_lowest_z)  # 10, -40, 2.5
        self.camera.set_pos(0, -64, self.camera_lowest_z)
        # self.camera.setPos(10, -40, 30)
        # self.camera.set_p(10)
        # self.camera.look_at(-2, 12, self.camera_lowest_z + 4 * 2.5)
        self.camera.look_at(0, 0, self.camera_lowest_z + 4 * 2.5)

    def moveup_camera(self, dt):
        angle = dt * 100
        vertical_distance = 15 * dt

        if (nagivator_h := self.navigator.get_h()) < 360:
            self.navigator.set_h(nagivator_h + angle)
        elif nagivator_h > 360:
            self.navigator.set_h(360)

        if (camera_z := self.camera.get_z()) < self.camera_highest_z:
            self.camera.set_z(camera_z + vertical_distance)
        elif camera_z > self.camera_highest_z:
            self.camera.set_z(self.camera_highest_z)

        if nagivator_h == 360 and camera_z == self.camera_highest_z:
            return False

        return True

    def control_mouse(self):
        if self.mouseWatcherNode.has_mouse():
            mouse_pos = self.mouseWatcherNode.get_mouse()
            near_pos = Point3()
            far_pos = Point3()
            self.camLens.extrude(mouse_pos, near_pos, far_pos)
            from_pos = self.render.get_relative_point(self.camera, near_pos)
            to_pos = self.render. get_relative_point(self.camera, far_pos)
            result = self.world.ray_test_closest(from_pos, to_pos, BitMask32.bit(1))

            if result.hasHit():
                if (nd := result.get_node()).is_active():
                    clicked_pos = result.get_hit_pos()
                    return clicked_pos, NodePath(nd)

                # node_name = result.get_node().get_name()
                # clicked_pos = result.get_hit_pos()

                # if (block := self.tower.blocks.find(node_name)).node().is_active():
                #     return clicked_pos, block
            else:
                self.mouse_x = 0
                self.mouse_dragging = globalClock.get_frame_count() + WAIT_COUNT
        return None

    def mouse_click(self):
        self.click = True

    def mouse_release(self):
        self.mouse_dragging = 0

    def rotate(self, rotation_angle):
        q = Quat()
        axis = Vec3.up()
        q.setFromAxisAngle(rotation_angle, axis.normalized())
        r = q.xform(self.camera.getPos() - self.scene.foundation.get_pos(self.render))
        rotated_pos = self.scene.foundation.get_pos(self.render) + r
        return rotated_pos

    def control_rotation(self, dt):
        mouse_x = self.mouseWatcherNode.get_mouse_x()
        if globalClock.get_frame_count() >= self.mouse_dragging:
            angle = 0
            if (delta := mouse_x - self.mouse_x) < 0:
                angle += 90
            elif delta > 0:
                angle -= 90
            angle *= dt

            # rotated_pos = self.tower.rotate(self.camera, angle)
            # rotated_pos = self.rotate(angle)
            # self.camera.setPos(rotated_pos)
            # self.camera.setH(self.camera.getH() + angle)
            self.navigator.set_h(self.navigator.get_h() + angle)
            # self.ball.reposition(rotation_angle=angle)

        self.mouse_x = mouse_x

    def control_descent(self, dt):
        if self.camera.get_z() > self.camera_lowest_z:
            if self.camera.get_z() > self.tower.floater.get_z(self.render):
                distance = 10 * dt
                self.camera.set_z(self.camera.get_z() - distance)
                self.ball.reposition(vertical_distance=distance)

        
        # if self.camera.get_z() > self.camera_lowest_z:
        #     distance = 10 * dt
           
        #     self.camera.set_z(self.camera.get_z() - distance)
        #     self.descent_distance -= distance
        #     self.ball.reposition(vertical_distance=distance)

    def clear(self):
        if self.tower.tower_top <= 0:
            self.gameover_seq.append(Func(self.tower.clear_foundation, self.bubbles))
        self.gameover_seq.append(Wait(2))
        self.gameover_seq.start()

    def game_over(self):
        if self.tower.tower_top <= 0:
            self.tower_num += 1
        if self.tower_num >= len(towers):
            self.tower_num = 0

        self.tower.remove_blocks()
        self.initialize_game()

    def update(self, task):
        dt = globalClock.getDt()
        self.scene.water_camera.setMat(self.cam.getMat(self.render) * self.scene.clip_plane.getReflectionMat())

        if self.state == Game.START:
            if not self.moveup_camera(dt):
                self.ball.setup(Colors.select(), self.camera)
                self.state = Game.PLAY

        if self.state == Game.CLEAR:
            self.clear()
            self.state = Game.GAMEOVER

        if self.state == Game.GAMEOVER:
            if not self.gameover_seq.is_playing():
                self.game_over()

        if self.state == Game.PLAY:
            if self.click:
                if clicked := self.control_mouse():
                    self.ball.move(*clicked)
                self.click = False

            if self.tower.tower_top <= 0 or self.ball.cnt == 0:
                self.state = Game.CLEAR

            # self.tower.floating(self.world.contact_test(self.scene.surface.node()))
            self.tower.sink(self.world.contact_test(self.scene.bottom.node()))
            
            # if task.time >= self.timer:
            #     self.tower.update()
            #     self.timer = task.time + CHECK_REPEAT
            self.tower.update()
            
            # activated_rows = 0
            # if task.time >= self.timer:
            #     activated_rows = self.tower.update()
            #     self.timer = task.time + CHECK_REPEAT

            # activated_rows = self.tower.update()
            # # self.descent_distance += activated_rows * self.tower.block_h
            # self.descent_distance += activated_rows * 3.14
            # if self.descent_distance > 0:
            #     self.control_descent(dt)
            self.control_descent(dt)

            if self.mouse_dragging:
                self.control_rotation(dt)

            if self.ball.state == Ball.DELETED and self.ball.cnt > 0:
                n = 7 if not self.ball.used else 6
                self.ball.setup(Colors.select(n), self.camera)

        self.world.do_physics(dt)
        return task.cont


class StartScreen(NodePath):

    def __init__(self, game):
        super().__init__(PandaNode('startScreen'))
        self.screen = OnscreenImage(
            image=PATH_START_SCREEN,
            parent=self,
            scale=(1.5, 1, 1),
            pos=(0, 0, 0)
        )
        self.button = DirectButton(
            pos=(0, 0, 0),
            scale=0.1,
            parent=self,
            frameSize=(-2, 2, -0.7, 0.7),
            frameColor=(0.75, 0.75, 0.75, 1),
            text="start",
            text_pos=(0, -0.3),
            command=self.click
        )
        self.game = game

    def _start(self):
        self.game.state = Game.START

    def click(self):
        self.detachNode()
        Sequence(Wait(0.5), Func(self._start)).start()


if __name__ == '__main__':
    game = TowerCrash()
    game.run()