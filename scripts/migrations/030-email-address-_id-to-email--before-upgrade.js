db.email_address.find().snapshot().forEach(function (e) {
    e.email = e._id;
    e._id = new ObjectId();
    db.email_address_new.insert(e);
    db.email_address.update({'_id': e._id}, {'migrated': true});
});