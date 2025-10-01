import os
from pathlib import Path
from detectron2.engine import DefaultTrainer
from detectron2.config import get_cfg
from detectron2.data.datasets import register_coco_instances
from detectron2 import model_zoo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "datasets" / "cards"
TRAIN_JSON = DATA / "annotations" / "train.json"
VAL_JSON   = DATA / "annotations" / "val.json"
TRAIN_IMG  = DATA / "images" / "train"
VAL_IMG    = DATA / "images" / "val"
OUT_DIR    = ROOT / "outputs" / "cards_r50"

def register():
    register_coco_instances("cards_train", {}, str(TRAIN_JSON), str(TRAIN_IMG))
    register_coco_instances("cards_val",   {}, str(VAL_JSON),   str(VAL_IMG))

def make_cfg():
    cfg = get_cfg()
    # Faster R-CNN (boxes). Good starter; upgrade to Mask R-CNN later if you want masks.
    cfg.merge_from_file(model_zoo.get_config_file(
        "COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"
    ))
    cfg.DATASETS.TRAIN = ("cards_train",)
    cfg.DATASETS.TEST  = ("cards_val",)
    cfg.DATALOADER.NUM_WORKERS = 2

    # Small-object friendly tweaks
    cfg.INPUT.MIN_SIZE_TRAIN = (720, 960, 1080)
    cfg.INPUT.MAX_SIZE_TRAIN = 1600
    cfg.INPUT.MIN_SIZE_TEST  = 1200
    cfg.INPUT.MAX_SIZE_TEST  = 1600
    cfg.MODEL.ANCHOR_GENERATOR.SIZES = [[8, 16, 32, 64, 128]]  # include tiny anchors

    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1  # 'card_front'
    cfg.MODEL.ROI_HEADS.BATCH_SIZE_PER_IMAGE = 128

    cfg.SOLVER.IMS_PER_BATCH = 2
    cfg.SOLVER.BASE_LR = 2.5e-4
    cfg.SOLVER.MAX_ITER = 4000  # start here; adjust as you add data
    cfg.SOLVER.STEPS = []       # no schedule to start

    cfg.MODEL.WEIGHTS = model_zoo.get_checkpoint_url(
        "COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.OUTPUT_DIR = str(OUT_DIR)
    # save the resolved config for inference later
    (OUT_DIR / "config_resolved.yaml").write_text(cfg.dump())
    return cfg

if __name__ == "__main__":
    assert TRAIN_JSON.exists() and VAL_JSON.exists(), "Put your COCO JSONs in datasets/cards/annotations/"
    register()
    cfg = make_cfg()
    trainer = DefaultTrainer(cfg)
    trainer.resume_or_load(resume=False)
    trainer.train()
