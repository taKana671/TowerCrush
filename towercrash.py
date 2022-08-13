from enum import Enum, auto

from direct.interval.IntervalGlobal import Sequence, Parallel, Func
from direct.showbase.ShowBaseGlobal import globalClock
from direct.showbase.ShowBase import ShowBase
from panda3d.bullet import BulletSphereShape
from panda3d.bullet import BulletWorld, BulletDebugNode
from panda3d.core import PandaNode, NodePath
from panda3d.core import Vec3, LColor, BitMask32, Point3
from panda3d.core import AmbientLight, DirectionalLight

from bubble import Bubbles
from scene import Scene
from tower import CylinderTower, ThinTower, Colors, Block


PATH_SPHERE = "models/sphere/sphere"


class Ball(Enum):

    DELETED = auto()
    READY = auto()
    MOVE = auto()


class ColorBall(NodePath):

    def __init__(self, tower):
        super().__init__(PandaNode('ball'))
        ball = base.loader.loadModel(PATH_SPHERE)
        ball.reparentTo(self)
        self.setScale(0.2)
        self.tower = tower
        self.state = None
        self.bubbles = Bubbles()

    def setup(self, camera_z):
        pos = Point3(5.5, -21, camera_z - 1.5)
        self.setPos(pos)
        self.setColor(Colors.select())
        self.reparentTo(base.render)
        self.state = Ball.READY

    def _delete(self):
        self.detachNode()
        self.state = Ball.DELETED

    def _hit(self, clicked_pos, block):
        para = Parallel(self.bubbles.get_sequence(self.getColor(), clicked_pos))

        if block.getColor() == self.getColor():
            para.append(Func(lambda: self.tower.crash(block, clicked_pos)))

        para.start()

    def move(self, clicked_pos, block):
        Sequence(
            self.posInterval(0.5, clicked_pos),
            Func(self._delete),
            Func(self._hit, clicked_pos, block)
        ).start()


class TowerCrash(ShowBase):

    def __init__(self):
        super().__init__()
        self.disableMouse()
        self.camera.setPos(20, -18, 30)
        # self.camera.setPos(10, -40, 2.5)  # 20, -18, 5
        self.camera.setP(10)
        self.camera.lookAt(5, 3, 5)  # 5, 0, 3
        # self.camera.lookAt(Point3(-2, 12, 12.5))  #10
        self.camera_lowest_z = 2.5

        self.setup_lights()
        self.physical_world = BulletWorld()
        self.physical_world.setGravity(Vec3(0, 0, -9.81))

        self.scene = Scene()
        self.scene.setup(self.physical_world)
        self.create_tower()

        camera_z = (self.tower.inactive_top + 1) * 2.5
        look_z = camera_z + 4 * 2.5
        self.camera.setPos(Point3(10, -40, camera_z))
        self.camera.lookAt(Point3(-2, 12, look_z))
        self.camera_move_distance = 0

        self.ball = ColorBall(self.tower)
        self.ball.setup(self.camera.getZ())

        self.dragging_duration = 0
        self.max_duration = 5

        # *******************************************
        collide_debug = self.render.attachNewNode(BulletDebugNode('debug'))
        self.physical_world.setDebugNode(collide_debug.node())
        collide_debug.show()
        # *******************************************

        self.accept('mouse1', self.click)
        self.accept('mouse1-up', self.release)
        self.taskMgr.add(self.update, 'update')

    def create_tower(self):
        center = Point3(-2, 12, 1.0)
        # self.tower = CylinderTower(center, 24, self.scene.foundation)
        self.tower = ThinTower(center, 16, self.scene.foundation, self.physical_world)
        self.tower.build(self.physical_world)

    def setup_lights(self):
        ambient_light = self.render.attachNewNode(AmbientLight('ambientLight'))
        ambient_light.node().setColor(LColor(0.6, 0.6, 0.6, 1))
        self.render.setLight(ambient_light)

        directional_light = self.render.attachNewNode(DirectionalLight('directionalLight'))
        directional_light.node().getLens().setFilmSize(200, 200)
        directional_light.node().getLens().setNearFar(1, 100)
        directional_light.node().setColor(LColor(1, 1, 1, 1))
        directional_light.setPosHpr(Point3(0, 0, 30), Vec3(-30, -45, 0))
        directional_light.node().setShadowCaster(True)
        self.render.setShaderAuto()
        self.render.setLight(directional_light)

    def click(self):
        self.dragging_duration = 0

        if self.mouseWatcherNode.hasMouse():
            mouse_pos = self.mouseWatcherNode.getMouse()
            near_pos = Point3()
            far_pos = Point3()
            self.camLens.extrude(mouse_pos, near_pos, far_pos)
            from_pos = self.render.getRelativePoint(self.camera, near_pos)
            to_pos = self.render.getRelativePoint(self.camera, far_pos)
            result = self.physical_world.rayTestClosest(from_pos, to_pos, BitMask32.bit(1))

            if result.hasHit():
                node_name = result.getNode().getName()
                clicked_pos = result.getHitPos()

                if (block := self.tower.blocks.find(node_name)).state in Block.TARGET:
                    self.ball.state = Ball.MOVE
                    self.ball.move(clicked_pos, block)

                print('node_name', node_name)
                print('collision_pt', clicked_pos)
            else:
                self.mouse_x = 0
                self.dragging_duration += 1

    def release(self):
        self.dragging_duration = 0

    def update(self, task):
        dt = globalClock.getDt()

        velocity = 0
        # control rotation of the tower
        if self.dragging_duration:
            mouse_x = self.mouseWatcherNode.getMouse().getX()
            if (delta := mouse_x - self.mouse_x) < 0:
                velocity -= 90
            elif delta > 0:
                velocity += 90
            self.mouse_x = mouse_x
            self.dragging_duration += 1

        if self.dragging_duration >= self.max_duration:
            self.tower.rotate_around(velocity * dt)

        # control dropped blocks
        for block in self.tower.blocks:

            if block.state in Block.MOVABLE:
                result = self.physical_world.contactTest(block.node())
                for contact in result.getContacts():
                    if contact.getNode1().getName() == self.scene.surface.name:
                        block.state = Block.INWATER
                        # self.physical_world.remove(block.node())
                        # block.removeNode()

            if block.state == Block.INWATER:
                self.physical_world.remove(block.node())
                block.state = Block.DELETE
                self.tower.cleanup(block)


        # setup next ball
        if self.ball.state == Ball.DELETED:
            self.ball.setup(self.camera.getZ())

        # control camera position
        distance = 0
        if cnt := self.tower.set_active():
            self.camera_move_distance += cnt * self.tower.block_h

        if self.camera_move_distance > 0:
            if self.camera.getZ() > self.camera_lowest_z:
                distance += 10
                self.camera_move_distance -= distance * dt
                self.camera.setZ(self.camera.getZ() - distance * dt)

                if self.ball.state == Ball.READY:
                    self.ball.setZ(self.ball.getZ() - distance * dt)

        self.physical_world.doPhysics(dt)
        return task.cont


if __name__ == '__main__':
    game = TowerCrash()
    game.run()
    # base = ShowBase()
    # base.setBackgroundColor(1, 1, 1)
    # base.disableMouse()
    # base.camera.setPos(0, -10, 5)
    # base.camera.lookAt(0, 0, 0)
    # cylinder = Cylinder()
    # cylinder.setPos(0, 0, 0)
    # cylinder.setColor(LColor(1, 0, 1, 1))
    # base.run()

