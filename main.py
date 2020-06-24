from src import multi_thread as mt
import logging
import os


if __name__ == "__main__":
    print("### START ###")
    mt.populate_db()
    print("###  DONE  ###")