/*
       Licensed to the Apache Software Foundation (ASF) under one
       or more contributor license agreements.  See the NOTICE file
       distributed with this work for additional information
       regarding copyright ownership.  The ASF licenses this file
       to you under the Apache License, Version 2.0 (the
       "License"); you may not use this file except in compliance
       with the License.  You may obtain a copy of the License at

         http://www.apache.org/licenses/LICENSE-2.0

       Unless required by applicable law or agreed to in writing,
       software distributed under the License is distributed on an
       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
       KIND, either express or implied.  See the License for the
       specific language governing permissions and limitations
       under the License.
*/

db.email_address_old.find({'migrated': {'$ne': true}}).snapshot().forEach(function (e) {
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address.insert(e);
    db.email_address_old.update({'_id': e.email}, {$set: {migrated: true}});
});
// Drop the collection manually if everything is okay
// db.email_address_old.drop();
