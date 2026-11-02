# -*- coding: utf-8 -*-
"""Download the compact Fruits-360 100x100 dataset via kagglehub."""
from kagglehub import dataset_download


def main():
    print(dataset_download("ishandandekar/fruitimagedataset"))


if __name__ == "__main__":
    main()
