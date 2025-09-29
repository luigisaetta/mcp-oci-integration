"""
File name: db_utils.py
Author: Luigi Saetta
Date last modified: 2025-07-30
Python Version: 3.11

Description:
    This module contains utility functions for database operations,


Usage:
    Import this module into other scripts to use its functions.
    Example:
        import config

License:
    This code is released under the MIT License.

Notes:
    This is a part of a demo showing how to implement an advanced
    RAG solution as a LangGraph agent.

Warnings:
    This module is in development, may change in future versions.
"""

import oracledb

from config_private import CONNECT_ARGS


def get_connection():
    """
    get a connection to the DB
    """
    return oracledb.connect(**CONNECT_ARGS)


def list_collections():
    """
    return a list of all collections (tables) with a type vector
    in the schema in use
    """

    query = """
                SELECT DISTINCT table_name
                FROM user_tab_columns
                WHERE data_type = 'VECTOR'
                ORDER by table_name ASC
                """
    _collections = []
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)

            rows = cursor.fetchall()

            for row in rows:
                _collections.append(row[0])

    return sorted(_collections)


def list_books_in_collection(collection_name: str) -> list:
    """
    get the list of books/documents names in the collection
    taken from metadata
    expect metadata contains the field source

    modified to return also the numb. of chunks
    """
    query = f"""
                SELECT DISTINCT json_value(METADATA, '$.source') AS books, 
                count(*) as n_chunks 
                FROM {collection_name}
                group by books
                ORDER by books ASC
                """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)

            rows = cursor.fetchall()

            list_books = []
            for row in rows:
                list_books.append((row[0], row[1]))

    return sorted(list_books)


def fetch_text_by_id(id: str, collection_name: str) -> str:
    """
    Given the ID of a chunk return the text
    """
    sql = """
    SELECT TEXT, json_value(METADATA, '$.source')
    FROM {collection_name}
    WHERE ID = :id
    """

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.format(collection_name=collection_name),
                {"id": id},
            )

            # we expect 0 or 1 rows
            row = cursor.fetchone()
            if row:
                clob = row[0]
                text_value = clob.read() if clob is not None else None
                source = row[1]
            else:
                source = None
                text_value = None

    return {"text_value": text_value, "source": source}
