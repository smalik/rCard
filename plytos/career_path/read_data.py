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

# Settings used to connect to the Mongo instance holding
# data scraped from Indeed
settings = {
    'mongo_host': 'localhost',
    'mongo_db_name': 'resume',
    'mongo_collection_name': 'resume',
    'mongo_port': 27017,
    'chunk_size': 10000,
    'drop_collections_on_load'    : True,
}

def _apply_func(r, f):
    """Helper function that applies a given function to all
    the sentences held in the Redis DB

    Keyword arguments:
    r -- Reddis DB connection
    f -- Lambda function to be applied to objects in DB
    """

    for key in r.keys():
        sentences = r.lrange(key, start=0, end=-1)
        result = []
        for sentence in sentences:
            result.append(f(sentence.decode('utf8')))
        r.delete(key)
        r.lpush(key, *result)

#################### Basic Formatting/Clean ########################
def _rem_stop(sentences, stops=stopwords.words("english")):
    """Removes all the stopwords from each sentence of the passed-in
    list, returning this list. Uses the NLTK stopwords by default

    Keyword arguments:
    sentences -- List of strings (sentences)
    stops -- List of stopwords to be removed (English NLTK by default)
    """
    return [" ".join([word for word in sentence.split() if 
        word not in stops]) for sentence in sentences]

def _rem_punc(sentences):
    """Helper function that removes all punctuation from each 
    sentence of the passed-in list, returning this list

    Keyword arguments:
    sentences -- List of strings (sentences)
    """
    return [sentence.translate(string.punctuation) 
        for sentence in sentences]

def _lower_words(sentences):
    """Helper function that converts all case to lower for each 
    sentence of the passed-in list, returning this list

    Keyword arguments:
    sentences -- List of strings (sentences)
    """
    return [sentence.lower() for sentence in sentences]

###################### Transform to Bases ###########################
def _stem_values(sentences, stemmer):
    """Helper function that stems words from each sentence 
    of the passed-in list, returning this list

    Keyword arguments:
    sentences -- List of strings (sentences)
    stemmer -- NLTK stemmer object to be applied
    """
    return [" ".join([stemmer.stem(word) 
        for word in sentence.split()]) for sentence in sentences]

def _lemmatize_values(sentences):
    """Helper function that lemmatizes words from each 
    sentence of the passed-in list (using NLTK WordNet), returning this list

    Keyword arguments:
    sentences -- List of strings (sentences)
    """
    wordnet_lemmatizer = WordNetLemmatizer()
    return [" ".join([wordnet_lemmatizer.lemmatize(word) 
        for word in sentence.split()]) for sentence in sentences]

####################### Generate n-Grams ############################
def _gen_ngrams(sentences, n):
    """Helper function that generates n-grams from each 
    sentence of the passed-in list, returning this list

    Keyword arguments:
    sentences -- List of strings (sentences)
    """
    return [[sentence[i:] for i in range(n)]
        for sentence in sentences]

def push_chunk(chunk):
    """Pushes the chunk after processing it/transforming, into
    the Redis DB -- transformations can be set via flags

    Keyword arguments:
    chunk -- Chunk (pointer) of the Mongo collection
    """
    r = redis.StrictRedis(host='localhost', port=6379, db=0)

    query_col = "_id"
    stem_map = {
        "lancaster": LancasterStemmer(),
        "porter": PorterStemmer(),
        "snowball": SnowballStemmer('english')
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

    df    =  pd.DataFrame(list(chunk))
    for (experience, _id) in zip(df["experience"], df[query_col]):
        for item in experience['_values']['items']:
            description = item['_values']['description']
            post_translate = description.translate(string.punctuation)
            sentences = sent_tokenize(post_translate)

            if set_case:
                sentences = _lower_words(sentences)

            if remove_stopwords:
                sentences = _rem_stop(sentences)

            if remove_punctuation:
                sentences = _rem_punc(sentences)

            if stem_lemma == "stem":
                sentences = _stem_values(sentences, stemmer=stem_map[which_stemmer])
            elif stem_lemma == "lemma":
                sentences = _lemmatize_values(sentences)

            if generate_ngrams:
                n = 3
                sentences = _gen_ngrams(sentences, n)

            for sentence in sentences:
                if glen(sentence) > 0:
                    r.lpush(_id, sentence.encode('utf8'))

def chunk_mongo(db, collection, host, port, query={}):
    """Separates the Mongo database into chunks (set in the
    top settings) and returns as a list

    Keyword arguments:
    db -- Name of database connecting to (default: localhost)
    collection -- Name of collection in DB (default: resume)
    host -- Name of host of connection (default: resume)
    port -- Port by which connection to the DB made (default: 27107)
    query -- String of request being made from the DB
    """
    # Connect to MongoDB
    db = MongoClient(host, port)[db]

    # Make a query to the specific DB and Collection
    cursor = db[collection].find(query)
    query_results = cursor.count()
    
    chunks = []
    for start in range(0, query_results, settings["chunk_size"]):
        chunks.append([list(cursor[start : start + settings["chunk_size"]])])
    return chunks

def transform_db():
    """Transforms the MongoDB into Reddis DB (with transformations
    specified by flags above) for generating training corpus
    """
    print("Reading Data...")
    chunks = chunk_mongo(
        db = settings["mongo_db_name"],
        collection = settings["mongo_collection_name"],
        host = settings["mongo_host"],
        port = settings["mongo_port"],
        query = {},
    )

    pool = multiprocessing.Pool(multiprocessing.cpu_count())
    pool.starmap_async(push_chunk, chunks).get()

if __name__ == "__main__":
    transform_db()