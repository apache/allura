db.email_address_old.find({'migrated': {'$ne': false}}).snapshot().forEach(function (e) {
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address.insert(e);
    db.email_address_old.update({'_id': e._id}, {'migrated': true});
});
// Drop the collection manually if everything is okay
// db.email_address_old.drop();