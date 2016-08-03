"""
read_data.py: Transforms the test data into a redis database for
creating a training corpus for word2vec

__author__ = "Yash Patel"
__copyright__ = "Copyright 2016, Plytos Inc."

__license__ = "Free/Open"
__version__ = "1.0.0"
__maintainer__ = "Yash Patel"
__email__ = "ypatel@princeton.edu"
"""

from nltk.tokenize import sent_tokenize
from nltk.corpus import stopwords

from nltk.stem import WordNetLemmatizer

from nltk.stem.lancaster import LancasterStemmer
from nltk.stem.porter import PorterStemmer
from nltk.stem.snowball import SnowballStemmer

import pandas as pd
from pymongo import MongoClient
import redis

import string
import re
import multiprocessing

settings = {
    'mongo_host': 'localhost',
    'mongo_db_name': 'resume',
    'mongo_collection_name': 'resume',
    'mongo_port': 27017,
    'chunk_size': 10000,
    'drop_collections_on_load'    : True,
}

def _apply_func(r, f):
    for key in r.keys():
        sentences = r.lrange(key, start=0, end=-1)
        result = []
        for sentence in sentences:
            result.append(f(sentence.decode('utf8')))
        r.delete(key)
        r.lpush(key, *result)

#################### Basic Formatting/Clean ########################
def _rem_stop(r, stops=stopwords.words("english")):
    _apply_func(r, lambda sentence : " ".join([word for word in 
        sentence.split() if word not in stops]))

def _rem_punc(r):
    _apply_func(r, lambda sentence : 
        sentence.translate(string.punctuation))

def _lower_words(r):
    _apply_func(r, lambda sentence : sentence.lower())

###################### Transform to Bases ###########################
def _stem_values(r, stemmer):
    _apply_func(r, lambda sentence : " ".join([stemmer.stem(word) 
        for word in sentence.split()]))

def _lemmatize_values(r):
    wordnet_lemmatizer = WordNetLemmatizer()
    _apply_func(r, lambda sentence : " ".join([
        wordnet_lemmatizer.lemmatize(word) for word in  sentence.split()]))

####################### Generate n-Grams ############################
def _gen_ngrams(r, n):
    _apply_func(r, lambda sentence : 
        [input_list[i:] for i in range(n)])

def _rem_encode(sent):
    regex = re.compile("[\\\\][^ ]+")
    no_encodes = regex.finditer(str(sent))
    cleaned_sent = []
    for encode in no_encodes:
        end = encode[0]
        cleaned_sent.append(sent[start:end])
        start = end
    end_segment = sent[start:end]
    if len(end_segment) > 0:
        cleaned_sent.append(end_segment)
    return " ".join(cleaned_sent)

def push_chunk(chunk):
    df    =  pd.DataFrame(list(chunk))
    for (experience, _id) in zip(df["experience"], df[query_col]):
        for item in experience['_values']['items']:
            description = item['_values']['description']
            description = description.translate(string.punctuation)
            sentences = sent_tokenize(description)
            for sent in sentences:
                if len(sent) > 0:
                    r.rpush(_id, sent.encode('utf8'))

""" Read from Mongo and Store into DataFrame """
def read_mongo(r, db, collection, host, port, query={}):
    query_col = "_id"
    keep = ['sentences', query_col]
    # Connect to MongoDB
    db = MongoClient(host, port)[db]

    # Make a query to the specific DB and Collection
    cursor = db[collection].find(query)
    query_results = cursor.count()
    r.flushall()

    # Expand the cursor and construct the DataFrame
    chunks = []
    pool = multiprocessing.Pool(multiprocessing.cpu_count())

    for start in range(0, query_results, settings["chunk_size"]):
        chunks.append((cursor[start : start + settings["chunk_size"]]))
    pool.starmap_async(push_chunk, chunks)

def transform_db():
    r = redis.StrictRedis(host='localhost', port=6379, db=0)
    stem_map = {
        "Lancaster": LancasterStemmer(),
        "Porter": PorterStemmer(),
        "Snowball": SnowballStemmer()
    }

    #################### Binary Flagging ########################
    # Set each of the following flags to either True/False
    set_case             = True
    remove_stopwords     = True
    remove_punctuation   = True
    generate_ngrams      = False

    #################### Binary Flagging ########################
    # Set each of the flags to one of the possible values given

    # lancaster, porter, snowball
    which_stemmer        = "snowball"

    # stem, lemma, other* (Anything)
    stem_lemma           = "stem"

    print("Reading Data...")
    read_mongo(
        r = r,
        db = settings["mongo_db_name"],
        collection = settings["mongo_collection_name"],
        host = settings["mongo_host"],
        port = settings["mongo_port"],
        query = {},
    )

    if set_case:
        print("Changing to Lower")
        _lower_words(r)

    if remove_stopwords:
        print("Removing Stopwords...")
        _rem_stop(r)

    if remove_punctuation:
        print("Removing Punctuation...")
        _rem_punc(r)

    if stem_lemma == "stem":
        print("Stemming Words...")
        _stem_values(r, stemmer=stem_map[which_stemmer])
    elif stem_lemma == "lemma":
        print("Lemmatizing Words...")
        _lemmatize_values(r)

    if generate_ngrams:
        print("Generating N-grams...")
        n = 3
        _gen_ngrams(r, n)

if __name__ == "__main__":
    transform_db()