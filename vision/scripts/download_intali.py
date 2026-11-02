# -*- coding: utf-8 -*-
"""Download the IntAli Food Dataset via kagglehub (anonymous download)."""
from kagglehub import dataset_download


def main():
    path = dataset_download("miketrs/intali-food-dataset")
    print(path)


if __name__ == "__main__":
    main()
