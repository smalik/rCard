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
from nltk.stem.lancaster import LancasterStemmer

import pandas as pd
from pymongo import MongoClient
import redis

import string

settings = {
    'mongo_host': 'localhost',
    'mongo_db_name': 'resume',
    'mongo_collection_name': 'resume',
    'mongo_port': 27017,
    'chunk_size': 10000,
    'drop_collections_on_load'    : True,
}

def __apply_func(r, f):
    stops = stopwords.words("english")
    for key in r.keys():
        sentences = r.get(key)
        result = []
        for sentence in sentences:
            result.append(f(sentence))
        r.set(key, result)

def _rem_stop(r):
    _apply_func(r, lambda sentence : " ".join([word for word in 
        sentence.split() if word not in stops]))

def _stem_values(r):
    st = LancasterStemmer()
    _apply_func(r, lambda sentence : " ".join([st.stem(word) for word 
        in sentence.split()]))

def _rem_punc(r):
    _apply_func(r, 
        lambda sentence : sentence.translate(string.punctuation))

def find_ngrams(input_list, n):
    return zip(*[input_list[i:] for i in range(n)])

def _gen_ngrams(r, n):
    _apply_func(r, 
        lambda sentence : find_ngrams(sentence.split(), n))

""" Read from Mongo and Store into DataFrame """
def read_mongo(r, db, collection, host, port, query={}):
    query_col = "_id"
    keep = ['sentences', query_col]

    # Connect to MongoDB
    db = MongoClient(host, port)[db]

    # Make a query to the specific DB and Collection
    cursor = db[collection].find(query)
    query_results = cursor.count()
    
    # Expand the cursor and construct the DataFrame
    for start in range(0, query_results, settings["chunk_size"]):
        chunk = list(cursor[start : start + settings["chunk_size"]])
        df    =  pd.DataFrame(chunk)
        for (experience, _id) in zip(df["experience"], df[query_col]):
            exp_sentences = []
            for item in experience['_values']['items']:
                description = item['_values']['description']
                description = description.translate(string.punctuation)

                sentences = sent_tokenize(description)
                clean_sent = [sent for sent in sentences if len(sent) > 0]
                exp_sentences.append(clean_sent)
            r.set(_id, exp_sentences)
            # pd.read_msgpack(redisConn.get("key"))
    return df

if __name__ == "__main__":
    r = redis.StrictRedis(host='localhost', port=6379, db=0)

    read_mongo(
        r = r,
        db = settings["mongo_db_name"],
        collection = settings["mongo_collection_name"],
        host = settings["mongo_host"],
        port = settings["mongo_port"],
        query = {},
    )
    _rem_stop(r)
    _stem_values(r)