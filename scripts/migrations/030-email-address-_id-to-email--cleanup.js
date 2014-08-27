db.email_address_old.find({'migrated': {'$ne': true}}).snapshot().forEach(function (e) {
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address.insert(e);
    db.email_address_old.update({'_id': e.email}, {$set: {migrated: true}});
});
// Drop the collection manually if everything is okay
// db.email_address_old.drop();
