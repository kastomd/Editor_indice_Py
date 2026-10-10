from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame, QFileDialog, QSpinBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QImage

TARGET       = 256
PRIO_DEF     = 3
PREVIEW_PX   = 400
PRIO_WEIGHTS = {1: 0.4, 2: 0.7, 3: 1.0, 4: 1.4, 5: 1.8}
PRIO_LABELS  = {1:"Min", 2:"Low", 3:"Normal", 4:"High", 5:"Max"}
PRIO_COLORS  = {1:"#e84060", 2:"#e88040", 3:"#e8c840", 4:"#80d860", 5:"#40d890"}
SLOT_COLORS  = [
    "#e8c840","#40c8e8","#e84060","#60e840",
    "#c040e8","#e88040","#40e8c0","#e86020",
    "#4080e8","#e840c0","#80e840","#e8e040",
]


class _R:
    __slots__ = ('x','y','w','h')
    def __init__(self,x,y,w,h): self.x,self.y,self.w,self.h=x,y,w,h

class MaxRects:
    def __init__(self,W,H):
        self.free=[_R(0,0,W,H)]; self.placed=[]

    def _split(self,F,P):
        if P.x>=F.x+F.w or P.x+P.w<=F.x or P.y>=F.y+F.h or P.y+P.h<=F.y:
            return [F]
        out=[]
        if P.x>F.x:          out.append(_R(F.x,F.y,P.x-F.x,F.h))
        if P.x+P.w<F.x+F.w: out.append(_R(P.x+P.w,F.y,F.x+F.w-(P.x+P.w),F.h))
        if P.y>F.y:          out.append(_R(F.x,F.y,F.w,P.y-F.y))
        if P.y+P.h<F.y+F.h: out.append(_R(F.x,P.y+P.h,F.w,F.y+F.h-(P.y+P.h)))
        return out

    def _prune(self):
        keep=[]
        for i,a in enumerate(self.free):
            if not any(j!=i and b.x<=a.x and b.y<=a.y
                       and b.x+b.w>=a.x+a.w and b.y+b.h>=a.y+a.h
                       for j,b in enumerate(self.free)):
                keep.append(a)
        self.free=keep

    def insert(self,w,h,rid):
        best=None; bs=float('inf')
        for f in self.free:
            if f.w>=w and f.h>=h:
                s=min(f.w-w,f.h-h)
                if s<bs: bs=s; best=f
        if not best: return False
        P=_R(best.x,best.y,w,h)
        nf=[]
        for f in self.free: nf.extend(self._split(f,P))
        self.free=nf; self._prune()
        self.placed.append((P.x,P.y,w,h,rid))
        return True


def _try_pack(orig_sizes, sfs):
    items=sorted(
        [(i,max(1,min(ow,int(ow*sf))),max(1,min(oh,int(oh*sf))))
         for i,((ow,oh),sf) in enumerate(zip(orig_sizes,sfs))],
        key=lambda t:t[1]*t[2], reverse=True
    )
    mr=MaxRects(TARGET,TARGET)
    for i,sw,sh in items:
        if not mr.insert(sw,sh,i): return None
    return mr.placed


def smart_pack(images, priorities):
    if not images: return []
    orig_sizes=[(img.width,img.height) for img in images]
    n=len(orig_sizes)
    weights=[PRIO_WEIGHTS[p] for p in priorities]
    avg_w=sum(weights)/n

    lo,hi=0.0,20.0; best_k=0.001
    for _ in range(70):
        mid=(lo+hi)/2
        sfs=[min(1.0, mid*weights[i]/avg_w) for i in range(n)]
        if _try_pack(orig_sizes,sfs): best_k=mid; lo=mid
        else: hi=mid

    scales=[min(1.0, best_k*weights[i]/avg_w) for i in range(n)]

    if not _try_pack(orig_sizes,scales):
        lo,hi=0.0,1.0; base=0.001
        for _ in range(60):
            mid=(lo+hi)/2
            if _try_pack(orig_sizes,[mid]*n): base=mid; lo=mid
            else: hi=mid
        scales=[base]*n

    by_prio_desc=sorted(range(n), key=lambda i: priorities[i], reverse=True)
    for idx in by_prio_desc:
        lo2,hi2=scales[idx],1.0
        for _ in range(50):
            mid=(lo2+hi2)/2; t=scales[:]; t[idx]=mid
            if _try_pack(orig_sizes,t): scales[idx]=mid; lo2=mid
            else: hi2=mid

    raw=_try_pack(orig_sizes,scales)
    if not raw: return []
    return [
        dict(orig_index=rid, x=x, y=y, w=w, h=h,
             orig_w=orig_sizes[rid][0], orig_h=orig_sizes[rid][1])
        for x,y,w,h,rid in raw
    ]


def _scale_no_bleed(img, tw, th):
    rgb=img.convert("RGB"); ow,oh=rgb.size
    padded=Image.new("RGB",(ow+2,oh+2))
    padded.paste(rgb,(1,1))
    padded.paste(rgb.crop((0,0,ow,1)),(1,0))
    padded.paste(rgb.crop((0,oh-1,ow,oh)),(1,oh+1))
    padded.paste(rgb.crop((0,0,1,oh)),(0,1))
    padded.paste(rgb.crop((ow-1,0,ow,oh)),(ow+1,1))
    padded.paste(rgb.crop((0,0,1,1)),(0,0))
    padded.paste(rgb.crop((ow-1,0,ow,1)),(ow+1,0))
    padded.paste(rgb.crop((0,oh-1,1,oh)),(0,oh+1))
    padded.paste(rgb.crop((ow-1,oh-1,ow,oh)),(ow+1,oh+1))
    scaled=padded.resize((tw+2,th+2),Image.LANCZOS)
    return scaled.crop((1,1,tw+1,th+1))


def build_atlas(images, pack_result):
    atlas=Image.new("RGB",(TARGET,TARGET),(0,0,0))
    for info in pack_result:
        tile=_scale_no_bleed(images[info["orig_index"]],info["w"],info["h"])
        atlas.paste(tile,(info["x"],info["y"]))
    return atlas


def _pil_to_qpixmap(img: Image.Image) -> QPixmap:
    img_rgba=img.convert("RGBA")
    data=img_rgba.tobytes("raw","RGBA")
    qimg=QImage(data,img_rgba.width,img_rgba.height,QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def _draw_labels(img: Image.Image, pack_result, scale) -> Image.Image:
    overlay=img.copy().convert("RGBA")
    draw=ImageDraw.Draw(overlay)
    color_map={info["orig_index"]:i for i,info in enumerate(pack_result)}
    for info in pack_result:
        n=info["orig_index"]+1
        col=SLOT_COLORS[color_map[info["orig_index"]]%len(SLOT_COLORS)]
        x=int(info["x"]*scale); y=int(info["y"]*scale)
        w=int(info["w"]*scale); h=int(info["h"]*scale)
        fs=max(9,min(w,h)//3)
        try: font=ImageFont.truetype("arial.ttf",fs)
        except:
            try: font=ImageFont.truetype("DejaVuSans-Bold.ttf",fs)
            except: font=ImageFont.load_default()
        cx,cy=x+w//2,y+h//2
        for dx,dy in [(-1,-1),(1,-1),(-1,1),(1,1),(0,-1),(0,1),(-1,0),(1,0)]:
            draw.text((cx+dx,cy+dy),str(n),font=font,fill=(0,0,0,210),anchor="mm")
        draw.text((cx,cy),str(n),font=font,fill=col,anchor="mm")
    return overlay


class TexturePackerWindow(QDialog):
    def __init__(self, parent, tex_map: dict, on_proceed):
        super().__init__(parent)
        self.setWindowTitle("BT3 → TTT · Texture Packer")
        self.setModal(True)
        self.setMinimumSize(860, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        if parent:
            self.setWindowIcon(parent.windowIcon())
            self.setFont(parent.font())

        self._on_proceed  = on_proceed
        self.tex_id_order = list(tex_map.keys())
        self.images       = [tex_map[tid] for tid in self.tex_id_order]
        self.priorities   = [PRIO_DEF] * len(self.images)
        self.pack_result  = []
        self.composed     = None
        self._show_nums   = True
        self._row_widgets = []

        self._build_ui()
        self._center_on_parent(parent)
        self.do_pack()

    def _center_on_parent(self, parent):
        if not parent: return
        pg=parent.geometry()
        self.adjustSize()
        self.move(pg.x()+(pg.width()-self.width())//2,
                  pg.y()+(pg.height()-self.height())//2)

    def _build_ui(self):
        root=QHBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(12,12,12,12)

        left=QVBoxLayout(); left.setSpacing(6)
        lbl=QLabel("ATLAS  256×256")
        lbl.setStyleSheet("font-size: 10px; color: #555;")
        lbl.setAlignment(Qt.AlignCenter)
        left.addWidget(lbl)

        self._canvas=QLabel()
        self._canvas.setFixedSize(PREVIEW_PX,PREVIEW_PX)
        self._canvas.setStyleSheet("background: #060610; border: 1px solid #1a1a2e;")
        self._canvas.setAlignment(Qt.AlignCenter)
        left.addWidget(self._canvas)

        self._lbl_cov=QLabel("Coverage: —")
        self._lbl_cov.setAlignment(Qt.AlignCenter)
        self._lbl_cov.setStyleSheet("font-size: 11px; color: #e8c840;")
        left.addWidget(self._lbl_cov)

        self._btn_nums=QPushButton("Numbers: ON")
        self._btn_nums.setFixedHeight(26)
        self._btn_nums.setCheckable(True)
        self._btn_nums.setChecked(True)
        self._btn_nums.setFocusPolicy(Qt.NoFocus)
        self._btn_nums.clicked.connect(self._toggle_nums)
        left.addWidget(self._btn_nums)
        left.addStretch()
        root.addLayout(left, 0)

        right=QVBoxLayout(); right.setSpacing(6)

        self._btn_ok=QPushButton("✔  Port PMDL")
        self._btn_ok.setFixedHeight(36)
        self._btn_ok.setStyleSheet("font-weight: bold; color: #80ff9a; background: #1e4d2a;")
        self._btn_ok.setFocusPolicy(Qt.NoFocus)
        self._btn_ok.clicked.connect(self._on_ok)
        right.addWidget(self._btn_ok)

        btn_repack=QPushButton("▶  Recalculate")
        btn_repack.setFixedHeight(28)
        btn_repack.setFocusPolicy(Qt.NoFocus)
        btn_repack.clicked.connect(self.do_pack)
        right.addWidget(btn_repack)

        lbl_hint=QLabel("1 = Min    3 = Normal    5 = Max priority")
        lbl_hint.setStyleSheet("font-size: 10px; color: #444;")
        right.addWidget(lbl_hint)

        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_container=QWidget()
        self._list_layout=QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(4)
        self._list_layout.setContentsMargins(4,4,4,4)
        self._list_layout.addStretch()
        scroll.setWidget(self._list_container)
        right.addWidget(scroll, 1)
        root.addLayout(right, 1)
        self._rebuild_list()

    def _rebuild_list(self):
        for w in self._row_widgets: w.setParent(None)
        self._row_widgets.clear()
        self._list_layout.takeAt(self._list_layout.count()-1)

        for i,(tid,img) in enumerate(zip(self.tex_id_order,self.images)):
            info=next((p for p in self.pack_result if p["orig_index"]==i),None)
            col=SLOT_COLORS[i%len(SLOT_COLORS)]

            row=QFrame()
            row.setStyleSheet("background: #1a1a28; border-radius: 4px;")
            rl=QHBoxLayout(row)
            rl.setContentsMargins(6,4,6,4); rl.setSpacing(6)

            stripe=QFrame()
            stripe.setFixedWidth(4)
            stripe.setStyleSheet(f"background: {col}; border-radius: 2px;")
            rl.addWidget(stripe)

            lbl_n=QLabel(str(i+1))
            lbl_n.setFixedWidth(20)
            lbl_n.setAlignment(Qt.AlignCenter)
            lbl_n.setStyleSheet(f"color: {col}; font-weight: bold; font-size: 12px;")
            rl.addWidget(lbl_n)

            thumb=img.copy(); thumb.thumbnail((32,32),Image.LANCZOS)
            lbl_t=QLabel()
            lbl_t.setFixedSize(36,36)
            lbl_t.setPixmap(_pil_to_qpixmap(thumb).scaled(36,36,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            rl.addWidget(lbl_t)

            info_col=QVBoxLayout(); info_col.setSpacing(1)
            lbl_tid=QLabel(tid[:24])
            lbl_tid.setStyleSheet("font-size: 11px; font-weight: bold; color: #ccc;")
            info_col.addWidget(lbl_tid)
            if info:
                lbl_sz=QLabel(f"orig {img.width}×{img.height}  →  {info['w']}×{info['h']}  @({info['x']},{info['y']})")
                lbl_sz.setStyleSheet("font-size: 10px; color: #60c880;")
            else:
                lbl_sz=QLabel(f"orig {img.width}×{img.height}  (no fit)")
                lbl_sz.setStyleSheet("font-size: 10px; color: #cc4444;")
            info_col.addWidget(lbl_sz)
            rl.addLayout(info_col,1)

            spin=QSpinBox()
            spin.setRange(1,5)
            spin.setValue(self.priorities[i])
            spin.setFixedWidth(48)
            spin.setFocusPolicy(Qt.NoFocus)
            spin.valueChanged.connect(lambda v,idx=i: self._set_prio(idx,v))
            rl.addWidget(spin)

            self._list_layout.insertWidget(self._list_layout.count(),row)
            self._row_widgets.append(row)

        self._list_layout.addStretch()

    def _set_prio(self,idx,val): self.priorities[idx]=val

    def _toggle_nums(self,checked):
        self._show_nums=checked
        self._btn_nums.setText("Numbers: ON" if checked else "Numbers: OFF")
        self._refresh_canvas()

    def _refresh_canvas(self):
        if not self.composed:
            self._canvas.clear(); return
        scale=PREVIEW_PX/TARGET
        disp=self.composed.resize((PREVIEW_PX,PREVIEW_PX),Image.NEAREST)
        if self._show_nums and self.pack_result:
            disp=_draw_labels(disp,self.pack_result,scale)
        self._canvas.setPixmap(_pil_to_qpixmap(disp))

    def do_pack(self):
        if not self.images: return
        self.pack_result=smart_pack(self.images,self.priorities)
        if not self.pack_result:
            self._lbl_cov.setText("Pack failed"); return
        self.composed=build_atlas(self.images,self.pack_result)
        self._refresh_canvas(); self._rebuild_list()
        cov=sum(p["w"]*p["h"] for p in self.pack_result)/TARGET**2
        self._lbl_cov.setText(f"Coverage: {cov*100:.1f}%  ({len(self.pack_result)}/{len(self.images)})")

    def _on_ok(self):
        if not self.composed or not self.pack_result: return
        atlas=self.composed.copy()
        result=list(self.pack_result)
        order=list(self.tex_id_order)
        self.accept()
        self._on_proceed(atlas,result,order)
