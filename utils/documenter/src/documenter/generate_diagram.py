from utilities.model import (
    EditionManuscriptLink, Origin, CorpusHagio, City, Library,
    Location, Manuscript, Provenance, Witness, Reference, Edition
)
from utilities.db import engine
from sqlalchemy_data_model_visualizer import generate_data_model_diagram
import os

models = [EditionManuscriptLink, Origin, CorpusHagio, City, Library, Location, Manuscript, Provenance, Witness, Reference, Edition]
output_file_name = '../data/hagiographies_model'
try:
    generate_data_model_diagram(models, output_file_name)
    os.remove(output_file_name)
except FileNotFoundError:
    print("Ignored xdg-open error")