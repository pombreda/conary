#
# Copyright (c) 2004 Specifix, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.opensource.org/licenses/cpl.php.
#
# This program is distributed in the hope that it will be useful, but
# without any waranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

from local import idtable
import versions
import time

class MetadataTable:

    METADATA_CLASS_SHORT_DESC = 0
    METADATA_CLASS_LONG_DESC = 1
    METADATA_CLASS_URL = 2
    METADATA_CLASS_LICENSE = 3
    METADATA_CLASS_CATEGORY = 4

    def __init__(self, db):
        self.db = db

        cu = self.db.cursor()
        cu.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")
        tables = [ x[0] for x in cu ]
        if 'Metadata' not in tables:
            cu.execute("""
                CREATE TABLE Metadata(metadataId INTEGER PRIMARY KEY,
                                      itemId INT,
                                      versionId INT,
                                      branchId INT,
                                      timeStamp INT)""")

        if 'MetadataItems' not in tables:
            cu.execute("""
                CREATE TABLE MetadataItems(metadataId INT,
                                           class INT,
                                           data STR,
                                           language STR)""")

    def add(self, itemId, versionId, branchId, shortDesc, longDesc,
            urls, licenses, categories, language):
        cu = self.db.cursor()

        cu.execute("""
            INSERT INTO Metadata (itemId, versionId, branchId, timestamp)
            VALUES(?, ?, ?, ?)""", itemId, versionId, branchId, time.time())
        mdId = cu.lastrowid
        
        for mdClass, data in (self.METADATA_CLASS_SHORT_DESC, [shortDesc]),\
                             (self.METADATA_CLASS_LONG_DESC, [longDesc]),\
                             (self.METADATA_CLASS_URL, urls),\
                             (self.METADATA_CLASS_LICENSE, licenses),\
                             (self.METADATA_CLASS_CATEGORY, categories):
            for d in data:
                cu.execute("""
                    INSERT INTO MetadataItems (metadataId, class, data, language)
                    VALUES(?, ?, ?, ?)""", mdId, mdClass, d, language)
            print "inserting"
        return mdId
