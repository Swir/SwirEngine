from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

from swirengine import Color, Game, Rectangle2D

BASE_DIR = Path(__file__).resolve().parent
ASSET_DIR = BASE_DIR / "assets"
os.chdir(BASE_DIR)

W, H = 1280, 720
FIXED_HZ = 120

PLAYER_W, PLAYER_H = 38.0, 60.0
RUN_SPEED = 350.0
GROUND_ACCEL = 2600.0
AIR_ACCEL = 1400.0
FRICTION = 3150.0
GRAVITY = -1870.0
JUMP_SPEED = 730.0
MAX_FALL = -1050.0

WORLD_LEFT, WORLD_RIGHT = -700.0, 4300.0
CAMERA_MIN = 0.0
CAMERA_MAX = WORLD_RIGHT - W/2
CAMERA_LEFT_DEAD = -330.0
CAMERA_RIGHT_DEAD = 245.0

GROUND_Y, GROUND_H = -250.0, 94.0
GROUND_TOP = GROUND_Y + GROUND_H/2
SPAWN_X = -450.0
SPAWN_Y = GROUND_TOP + PLAYER_H/2
CHECKPOINT_X = 2140.0
GOAL_X = 4050.0

SOLIDS = (
    (-450,-250,500,94,0),(40,-250,500,94,1),(540,-250,500,94,2),
    (1040,-250,500,94,0),(1540,-250,500,94,1),(2040,-250,500,94,2),
    (2540,-250,500,94,0),(3040,-250,500,94,1),(3540,-250,500,94,2),
    (4040,-250,900,94,0),
    (-120,-70,180,24,2),(260,12,190,24,1),(650,92,185,24,2),
    (1060,30,190,24,1),(1450,116,200,24,2),(1880,34,190,24,1),
    (2300,120,200,24,2),(2730,44,190,24,1),(3160,120,200,24,2),
    (3570,36,190,24,1),
)

CELLS = (
    (-450,-118),(-120,-26),(260,56),(650,136),(1060,74),(1450,160),
    (1880,78),(2300,164),(2730,88),(3160,164),(3570,80),
)

ENEMY_SPAWNS = (
    (160,-145,110,72),(820,-145,125,82),(1670,-145,140,92),
    (2470,-145,145,95),(3320,-145,130,98),
)

@dataclass
class Solid:
    x: float; y: float; w: float; h: float
    @property
    def left(self): return self.x-self.w/2
    @property
    def right(self): return self.x+self.w/2
    @property
    def bottom(self): return self.y-self.h/2
    @property
    def top(self): return self.y+self.h/2

@dataclass
class Enemy:
    frames_r: list
    frames_l: list
    shadow: object
    x: float
    y: float
    origin: float
    patrol: float
    speed: float
    direction: float = 1.0
    alive: bool = True
    phase: float = 0.0

    @property
    def all_frames(self):
        return self.frames_r + self.frames_l

@dataclass
class Cell:
    sprite: object
    glow: Rectangle2D
    active: bool = True

@dataclass
class Particle:
    node: Rectangle2D
    x: float; y: float; vx: float; vy: float
    life: float; max_life: float; size: float; color: Color

class NeonRoboRush16:
    def __init__(self):
        self.game = Game(
            "Neon Robo Rush v8 — 16-Bit Edition",
            W,H,mode="2d",target_fps=144,fixed_hz=FIXED_HZ,
            asset_root=ASSET_DIR,
        )

        self.px,self.py = SPAWN_X,SPAWN_Y
        self.vx=self.vy=0.0
        self.grounded=True
        self.last_grounded=True
        self.facing=1
        self.coyote=0.0
        self.jump_buffer=0.0
        self.invulnerable=0.0
        self.health=3
        self.energy=0
        self.total_energy=len(CELLS)
        self.won=False
        self.game_over=False
        self.checkpoint=(SPAWN_X,SPAWN_Y)
        self.checkpoint_active=False
        self.audio_ok=True
        self.time=0.0
        self.hero_anim_clock=0.0

        self._background()
        self._level()
        self._hero()
        self._enemies()
        self._cells()
        self._portal()
        self._particles()
        self._ui()

        self.game.camera.x=CAMERA_MIN
        self.game.camera.y=0.0

        self.game.fixed_update(self._fixed)
        self.game.update(self._update)

    def rect(self,x,y,w,h,color,**kw):
        return self.game.add(Rectangle2D(x,y,w,h,color,**kw))

    # ---------------- visuals ----------------
    def _background(self):
        self.sky=self.rect(0,0,1600,900,Color(.025,.035,.075,1),layer=-220)
        self.bg_far=[]
        self.bg_city=[]
        for i in range(4):
            self.bg_far.append(self.game.sprite("bg_far.png",x=i*1280,y=0,width=1280,height=720,layer=-215))
            self.bg_city.append(self.game.sprite("bg_city.png",x=i*1280,y=0,width=1280,height=720,layer=-210))

    def _level(self):
        self.solids=[]
        for i,(x,y,w,h,style) in enumerate(SOLIDS):
            self.solids.append(Solid(x,y,w,h))
            self.game.sprite(f"platform{style}.png",x=x,y=y,width=w,height=max(48,h+18),layer=-2)

        self.game.sprite("checkpoint.png",x=CHECKPOINT_X+20,y=-105,width=90,height=120,layer=5)
        self.checkpoint_glow=self.rect(CHECKPOINT_X+10,-70,26,26,Color(.18,.48,.65,.22),rotation=45,layer=4)

        # decorative pylons
        for x in (460,1260,2060,2860,3660):
            self.rect(x,-135,48,130,Color(.05,.13,.20,1),layer=2)
            self.rect(x,-88,58,8,Color(.10,.80,.88,.75),layer=3)

    def _hero(self):
        self.hero_shadow=self.game.sprite("shadow.png",x=self.px,y=self.py-44,width=82,height=28,layer=8)

        self.hero_frames={}
        specs = {
            "idle_r":["hero_idle0_r.png","hero_idle1_r.png"],
            "idle_l":["hero_idle0_l.png","hero_idle1_l.png"],
            "run_r":[f"hero_run{i}_r.png" for i in range(4)],
            "run_l":[f"hero_run{i}_l.png" for i in range(4)],
            "jump_r":["hero_jump_r.png"], "jump_l":["hero_jump_l.png"],
            "fall_r":["hero_fall_r.png"], "fall_l":["hero_fall_l.png"],
            "hit_r":["hero_hit_r.png"], "hit_l":["hero_hit_l.png"],
        }
        for state,names in specs.items():
            arr=[]
            for name in names:
                s=self.game.sprite(name,x=self.px,y=self.py+17,width=104,height=104,visible=False,layer=20)
                arr.append(s)
            self.hero_frames[state]=arr
        self.current_hero=None

    def _make_enemy_frame(self,texture,x,y,layer=15):
        return self.game.sprite(texture,x=x,y=y+13,width=82,height=82,visible=False,layer=layer)

    def _enemies(self):
        self.enemies=[]
        for x,y,patrol,speed in ENEMY_SPAWNS:
            rr=[self._make_enemy_frame("enemy0_r.png",x,y),self._make_enemy_frame("enemy1_r.png",x,y)]
            ll=[self._make_enemy_frame("enemy0_l.png",x,y),self._make_enemy_frame("enemy1_l.png",x,y)]
            sh=self.game.sprite("shadow.png",x=x,y=GROUND_TOP-6,width=58,height=20,layer=12)
            self.enemies.append(Enemy(rr,ll,sh,x,y,x,patrol,speed))

    def _cells(self):
        self.cells=[]
        for x,y in CELLS:
            glow=self.rect(x,y,48,48,Color(.14,1,.67,.12),rotation=45,layer=4)
            spr=self.game.sprite("power_cell.png",x=x,y=y,width=42,height=54,layer=6)
            self.cells.append(Cell(spr,glow))

    def _portal(self):
        self.portal_glow=self.rect(GOAL_X,-126,92,126,Color(.18,1,.68,.06),layer=3)
        self.portal=self.game.sprite("portal.png",x=GOAL_X,y=-120,width=108,height=154,layer=6)

    def _particles(self):
        self.particles=[]
        for _ in range(30):
            n=self.rect(-9999,-9999,6,6,Color(1,1,1,0),visible=False,layer=14)
            self.particles.append(Particle(n,-9999,-9999,0,0,0,1,6,Color(1,1,1,1)))

    def _ui(self):
        # small dark translucent HUD panels
        self.hud_panel=self.rect(-430,310,330,54,Color(.02,.05,.10,.76),screen_space=True,layer=90)
        self.obj_panel=self.rect(300,310,500,54,Color(.02,.05,.10,.72),screen_space=True,layer=90)
        self.hud=self.game.label("",-520,310,font_size=19)
        self.objective=self.game.label("",110,310,font_size=17)
        self.help=self.game.label("A/D or arrows: move   SPACE/W/UP: jump   R: restart",0,-330,font_size=14)
        self.banner=self.game.label("",0,235,font_size=30)
        self.subbanner=self.game.label("",0,198,font_size=16)

    # ---------------- collision ----------------
    @staticmethod
    def _overlap_1d(a0,a1,b0,b1):
        return a1>b0 and a0<b1

    def _player_box(self,x=None,y=None):
        x=self.px if x is None else x; y=self.py if y is None else y
        return (x-PLAYER_W/2,x+PLAYER_W/2,y-PLAYER_H/2,y+PLAYER_H/2)

    def _move_x(self,dt):
        dx=self.vx*dt
        if dx==0:return
        nx=max(WORLD_LEFT+PLAYER_W/2+3,min(WORLD_RIGHT-PLAYER_W/2-3,self.px+dx))
        l,r,b,t=self._player_box(nx,self.py)
        for s in self.solids:
            if not self._overlap_1d(b,t,s.bottom,s.top): continue
            if not self._overlap_1d(l,r,s.left,s.right): continue
            nx=s.left-PLAYER_W/2 if dx>0 else s.right+PLAYER_W/2
            self.vx=0
            l,r,b,t=self._player_box(nx,self.py)
        self.px=nx

    def _move_y(self,dt):
        self.last_grounded=self.grounded
        self.grounded=False
        dy=self.vy*dt; old_y=self.py; ny=self.py+dy
        ol,orr,ob,ot=self._player_box(self.px,old_y)
        nl,nr,nb,nt=self._player_box(self.px,ny)

        if dy<=0:
            best=None
            for s in self.solids:
                if not self._overlap_1d(nl,nr,s.left,s.right): continue
                if ob>=s.top-.01 and nb<=s.top:
                    best=s.top if best is None else max(best,s.top)
            if best is not None:
                ny=best+PLAYER_H/2; self.vy=0; self.grounded=True
        else:
            best=None
            for s in self.solids:
                if not self._overlap_1d(nl,nr,s.left,s.right): continue
                if ot<=s.bottom+.01 and nt>=s.bottom:
                    best=s.bottom if best is None else min(best,s.bottom)
            if best is not None:
                ny=best-PLAYER_H/2; self.vy=0
        self.py=ny

        if not self.grounded and self.vy<=0:
            feet=self.py-PLAYER_H/2
            for s in self.solids:
                if abs(feet-s.top)<=2 and self._overlap_1d(self.px-PLAYER_W*.32,self.px+PLAYER_W*.32,s.left,s.right):
                    self.grounded=True; self.py=s.top+PLAYER_H/2; self.vy=0; break

    # ---------------- FX ----------------
    def _sound(self,name,volume=.2):
        if not self.audio_ok:return
        try:self.game.sound(name,volume=volume)
        except RuntimeError:self.audio_ok=False

    def _spawn_particles(self,x,y,count,color,sx,sy,spread=1.0,size=6):
        emitted=0
        for p in self.particles:
            if p.life>0:continue
            a=(emitted/max(1,count-1)-.5)*spread
            p.x=x;p.y=y;p.vx=sx+a*120;p.vy=sy+abs(a)*60
            p.max_life=p.life=.30+abs(a)*.15;p.size=size;p.color=color;p.node.visible=True
            emitted+=1
            if emitted>=count:break

    def _update_particles(self,dt):
        for p in self.particles:
            if p.life<=0:
                p.node.visible=False;continue
            p.life-=dt
            if p.life<=0:
                p.node.visible=False;continue
            p.x+=p.vx*dt;p.y+=p.vy*dt;p.vy-=450*dt
            t=p.life/p.max_life
            p.node.x=p.x;p.node.y=p.y
            p.node.width=p.node.height=p.size*(.75+.25*t)
            p.node.color=Color(p.color.r,p.color.g,p.color.b,max(0,min(1,t*.9)))
            p.node.rotation+=dt*180

    # ---------------- gameplay ----------------
    def _fixed(self,dt):
        if self.won or self.game_over:return
        left=self.game.key("A") or self.game.key("LEFT")
        right=self.game.key("D") or self.game.key("RIGHT")
        move=float(right)-float(left)
        if move<0:self.facing=-1
        elif move>0:self.facing=1

        target=move*RUN_SPEED
        accel=GROUND_ACCEL if self.grounded else AIR_ACCEL
        if move:
            delta=target-self.vx;step=accel*dt;self.vx+=max(-step,min(step,delta))
        else:
            step=FRICTION*dt
            self.vx=0 if abs(self.vx)<=step else self.vx-math.copysign(step,self.vx)

        self.vy=max(MAX_FALL,self.vy+GRAVITY*dt)
        self._move_x(dt);self._move_y(dt)

        if self.grounded and not self.last_grounded:
            self._spawn_particles(self.px,self.py-PLAYER_H/2+2,4,Color(.7,.95,1,1),0,80,1.4,6)
        if self.py<-470:self._hurt()

    def _hurt(self):
        if self.invulnerable>0 or self.won or self.game_over:return
        self.health-=1;self._sound("hit.wav",.22)
        self._spawn_particles(self.px,self.py+8,6,Color(1,.32,.32,1),0,110,1.8,7)
        if self.health<=0:
            self.game_over=True;self.vx=self.vy=0;return
        self.px,self.py=self.checkpoint;self.vx=self.vy=0;self.grounded=True;self.invulnerable=1.15

    def _show_only(self,frames,index):
        for i,s in enumerate(frames):
            s.visible=(i==index)
            if s.visible:
                s.x=self.px;s.y=self.py+17

    def _hero_state(self):
        side="r" if self.facing>0 else "l"
        if self.invulnerable>0 and int(self.invulnerable*12)%2==0:
            return f"hit_{side}",0
        if not self.grounded:
            return (f"jump_{side}",0) if self.vy>=0 else (f"fall_{side}",0)
        if abs(self.vx)>25:
            idx=int(self.hero_anim_clock*12)%4
            return f"run_{side}",idx
        idx=int(self.hero_anim_clock*2)%2
        return f"idle_{side}",idx

    def _animate_hero(self,dt):
        self.hero_anim_clock+=dt
        state,idx=self._hero_state()
        for key,frames in self.hero_frames.items():
            for s in frames:s.visible=False
        fr=self.hero_frames[state]
        fr[idx].visible=True
        fr[idx].x=self.px;fr[idx].y=self.py+17
        fr[idx].rotation=(-2.0*self.facing if "run" in state else 0)

        self.hero_shadow.x=self.px
        self.hero_shadow.y=GROUND_TOP-6 if self.py<0 else self.py-45
        self.hero_shadow.width=82 if self.grounded else max(38,82-abs(self.vy)*.035)

    def _enemy_update(self,dt):
        for e in self.enemies:
            if not e.alive:continue
            e.phase+=dt*5
            e.x+=e.direction*e.speed*dt
            if e.x>e.origin+e.patrol or e.x<e.origin-e.patrol:e.direction*=-1
            frames=e.frames_r if e.direction>0 else e.frames_l
            idx=int(e.phase*1.5)%2
            for s in e.all_frames:s.visible=False
            frames[idx].visible=True
            frames[idx].x=e.x;frames[idx].y=GROUND_TOP+47+abs(math.sin(e.phase))*2
            e.shadow.x=e.x;e.shadow.y=GROUND_TOP-6

        pl,pr,pb,pt=self._player_box()
        for e in self.enemies:
            if not e.alive:continue
            ex=e.x;ey=GROUND_TOP+18
            el,er,eb,et=ex-19,ex+19,ey-19,ey+19
            if not(pr<el or pl>er or pt<eb or pb>et):
                if self.vy<-80 and pb>et-10:
                    e.alive=False
                    for s in e.all_frames:s.visible=False
                    e.shadow.visible=False;self.vy=450;self._sound("stomp.wav",.2)
                    self._spawn_particles(ex,ey+16,5,Color(1,.55,.18,1),0,90,1.4,6)
                else:self._hurt()
                break

    def _cell_update(self,dt):
        for i,(c,(x,y)) in enumerate(zip(self.cells,CELLS)):
            if not c.active:continue
            bob=math.sin(self.time*4+i)*5
            c.sprite.x=x;c.sprite.y=y+bob;c.sprite.rotation+=dt*18
            c.glow.x=x;c.glow.y=y+bob;c.glow.rotation+=dt*48
            if abs(self.px-x)<30 and abs(self.py-y)<43:
                c.active=False;c.sprite.visible=False;c.glow.visible=False;self.energy+=1
                self._sound("pickup.wav",.18)
                self._spawn_particles(x,y+8,5,Color(.4,1,.78,1),0,95,1.4,6)

        if not self.checkpoint_active and self.px>=CHECKPOINT_X:
            self.checkpoint_active=True;self.checkpoint=(CHECKPOINT_X,SPAWN_Y)
            self._sound("checkpoint.wav",.18)
            self._spawn_particles(CHECKPOINT_X+10,-70,6,Color(.35,1,.76,1),0,120,1.6,6)

        if self.energy==self.total_energy and abs(self.px-GOAL_X)<50:
            self.won=True;self.vx=self.vy=0;self._sound("win.wav",.2)
            self._spawn_particles(GOAL_X,-100,10,Color(.3,1,.8,1),0,140,2.2,7)

    # ---------------- camera / UI ----------------
    def _camera_update(self):
        cam=self.game.camera
        screen_x=self.px-cam.x
        if screen_x>CAMERA_RIGHT_DEAD:cam.x=self.px-CAMERA_RIGHT_DEAD
        elif screen_x<CAMERA_LEFT_DEAD:cam.x=self.px-CAMERA_LEFT_DEAD
        cam.x=max(CAMERA_MIN,min(CAMERA_MAX,cam.x));cam.y=0

        far0=cam.x*.16-640
        city0=cam.x*.34-640
        for i,s in enumerate(self.bg_far):s.x=far0+i*1280
        for i,s in enumerate(self.bg_city):s.x=city0+i*1280
        self.sky.x=cam.x

    def _portal_update(self,dt):
        unlocked=self.energy==self.total_energy
        self.portal.rotation=math.sin(self.time*1.7)*1.0
        self.portal_glow.color=Color(.18,1,.68,.13 if unlocked else .045)
        self.checkpoint_glow.rotation+=dt*55
        self.checkpoint_glow.color=Color(.22,1,.76,.38) if self.checkpoint_active else Color(.18,.48,.65,.22)

    def _ui_update(self):
        hearts="♥"*self.health+"·"*(3-self.health)
        self.hud.text=f"ROBO  {hearts}    ENERGY {self.energy}/{self.total_energy}"
        if self.won:
            self.objective.text="SECTOR CLEARED";self.banner.text="LEVEL COMPLETE";self.subbanner.text="NEON ROBO RUSH — 16-BIT EDITION"
        elif self.game_over:
            self.objective.text="SYSTEM OFFLINE";self.banner.text="GAME OVER";self.subbanner.text="Press R to restart"
        elif self.energy==self.total_energy:
            self.objective.text="PORTAL ONLINE — REACH THE GATE";self.banner.text="";self.subbanner.text=""
        else:
            self.objective.text="COLLECT ALL POWER CELLS";self.banner.text="";self.subbanner.text=""

    def _reset(self):
        self.px,self.py=SPAWN_X,SPAWN_Y;self.vx=self.vy=0;self.grounded=True;self.last_grounded=True
        self.facing=1;self.coyote=self.jump_buffer=self.invulnerable=0;self.health=3;self.energy=0
        self.won=self.game_over=False;self.checkpoint=(SPAWN_X,SPAWN_Y);self.checkpoint_active=False
        self.game.camera.x=CAMERA_MIN;self.game.camera.y=0
        for p in self.particles:p.life=0;p.node.visible=False
        for c in self.cells:c.active=True;c.sprite.visible=True;c.glow.visible=True;c.sprite.rotation=0
        for i,e in enumerate(self.enemies):
            x,y,_,_=ENEMY_SPAWNS[i];e.x=x;e.y=y;e.origin=x;e.direction=1;e.alive=True;e.shadow.visible=True
            for s in e.all_frames:s.visible=False

    def _update(self,dt):
        self.time+=dt;self.invulnerable=max(0,self.invulnerable-dt)
        if self.game.key_pressed("R"):self._reset()

        if not self.won and not self.game_over:
            self.coyote=.11 if self.grounded else max(0,self.coyote-dt)
            if self.game.key_pressed("SPACE") or self.game.key_pressed("W") or self.game.key_pressed("UP"):
                self.jump_buffer=.12
            else:self.jump_buffer=max(0,self.jump_buffer-dt)

            if self.jump_buffer>0 and self.coyote>0:
                self.vy=JUMP_SPEED;self.grounded=False;self.jump_buffer=0;self.coyote=0
                self._sound("jump.wav",.18)
                self._spawn_particles(self.px,self.py-PLAYER_H/2+6,4,Color(.55,.92,1,1),0,110,1.5,6)

            if (self.game.key_released("SPACE") or self.game.key_released("W") or self.game.key_released("UP")) and self.vy>250:
                self.vy*=.56

            self._enemy_update(dt);self._cell_update(dt)

        self._animate_hero(dt);self._update_particles(dt);self._camera_update();self._portal_update(dt);self._ui_update()

    def run(self):
        self.game.run()

if __name__=="__main__":
    NeonRoboRush16().run()
