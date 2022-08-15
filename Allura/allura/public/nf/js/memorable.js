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

/*global $, console, jQuery, localStorage */
window.Memorable = {};

/**
 * Class that describes the management of a memorable input - identifying, watching, saving, and restoring
 */
Memorable.InputManager = (function(){

    var defaults = {
        // regex to determine if an input's name can't reliably identify it, as many inputs have randomized
        // names for antispam purposes.
        invalidInputName: /([A-Za-z0-9\-_]{28})/,
        // selectors of buttons that represent a user cancellation, and will clear remembered inputs in the form
        cancelSelectors: '.cancel_edit_post, .cancel_form, input[value=Cancel]'
    };

    /**
     * @param inputObj - the InputBasic or InputMDE object representing the input to be tracked
     * @constructor
     */
    function InputManager(inputObj, options){
        this.options = $.extend({}, defaults, options);
        this.inputObj = inputObj;
        this.$form = this.inputObj.getForm();

        //watch the Input object for change
        this.inputObj.watchObj.on(this.inputObj.watchEvent, this.handleSave.bind(this));

        //watch "cancel"-style links, to forget immediately
        $(this.options.cancelSelectors, this.$form).on('click', this.handleCancel.bind(this));

        //watch for hidden inputs that might be revealed
        this.$form.on('replyRevealed', this.inputObj.refresh.bind(this.inputObj));

        //restore from localStorage
        this.restore();
    }

    /**
     * Builds a unique key to use when persisting the input's value
     * @returns {string}
     */
    InputManager.prototype.getStorageKey = function(){
        var self = this;
        function isUsableName($el){
            var name = $el.attr('name');
            if (name && !name.match(self.options.invalidInputName)){
                return true;
            }
        }
        function getRelativeAction($f){
            var action = $f[0].action;
            var list = action.split('/');
            var relativeAction = "/" + list.slice(3).join('/');
            return relativeAction;
        }

        var key = '';
        var $f = this.$form;
        var keySeparator = '__';
        if ($f.attr('action')){
            var relativeAction = getRelativeAction($f);
            key += relativeAction;
        }
        if (isUsableName(this.inputObj.$el)) {
            key += keySeparator + this.inputObj.$el.attr('name');
        } else if (this.inputObj.$el.attr('class')) {
            // id can't be relied upon, because of EW.  We can key off class, if it's the only one in the form.
            var klass = this.inputObj.$el.attr('class');
            if ($('.' + klass, $f).length == 1) {
                key += keySeparator + klass;
            } else {
                throw "Element isn't memorable, it has no unique class";
            }
        } else {
            throw "Element isn't memorable, it has no identifiable traits";
        }
        return key;
    };

    /**
     * Gets the value of the tracked input field
     */
    InputManager.prototype.getValue = function(){
        return this.inputObj.getValue();
    };

    /**
     * Saves the input's value to local storage, and registers it as part of the form for later removal
     */
    InputManager.prototype.save = function(){
        localStorage[this.getStorageKey()] = this.getValue();
    };

    /**
     * Event handler for invoking the save
     * @param e
     * @returns {boolean}
     */
    InputManager.prototype.handleSave = function(e){
        if (e.preventDefault){
            e.preventDefault();
        }
        this.save();
        return false;
    };

    /**
     * Event handler for clicking "cancel"
     * @param e
     * @returns {boolean}
     */
    InputManager.prototype.handleCancel = function(e){
        Memorable.forget(this.getStorageKey());
        return true;
    };
    /**
     * Fetches the tracked input's persisted value from storage
     * @returns {string}
     */
    InputManager.prototype.storedValue = function(){
        return localStorage[this.getStorageKey()];
    };

    /**
     * Fetches the input's remembered value and restores it to the target field
     */
    InputManager.prototype.restore = function(){
        if (!this.storedValue()){
            return;
        }
        this.inputObj.setValue(this.storedValue());
    };

    return InputManager;
})();


/**
 * Class describing a simple input field, as identified by a selector or DOM element, with specific methods for
 * getting & setting the value, and finding it's parent form
 *
 * @property obj: the raw object representing the field to be tracked; a standard jquery object
 * @property watchEvent: the name of the event to watch to detect when changes have been made
 * @property watchObj: the object instance to watch for events on. same as this.obj
 * @property $el: the jquery object representing the actual input field on the page. same as this.obj
 */
Memorable.InputBasic = (function() {
    /**
     * @param obj: a selector or DOM Element identifying the basic input field to be remembered
     * @constructor
     */
    function InputBasic(obj) {
        this.obj = $(obj);
        this.watchEvent = 'change';
        this.watchObj = this.obj;
        this.$el = this.obj;
    }
    InputBasic.prototype.getValue = function () {
        return this.obj.val();
    };
    InputBasic.prototype.setValue = function (val) {
        this.$el.val(val);
    };
    InputBasic.prototype.getForm = function () {
        return this.$el.parents('form').eq(0);
    };
    InputBasic.prototype.refresh = function(){
        return null;  // noop
    };
    return InputBasic;
})();


/**
 * Class describing a field backed by EasyMDE, as identified by the passed instance of `EasyMDE` provided, with specific methods for
 * getting & setting the value, and finding it's parent form
 *
 * @property obj: the EasyMDE object describing the field to be tracked
 * @property watchEvent: the name of the event to watch to detect when changes have been made
 * @property watchObj: the object instance to watch for events on; editor.codemirror per their docs
 * @property $el: the jquery object representing the actual input field on the page
 */
Memorable.InputMDE = (function() {
    /**
     * @param obj: A EasyMDE object representing the input field
     * @constructor
     */
    function InputMDE(obj) {
        this.obj = obj;
        this.watchEvent = 'change';
        this.watchObj = this.obj.codemirror;
        this.$el= $(this.obj.element);
    }
    InputMDE.prototype.getValue = function () {
        return this.obj.value();
    };
    InputMDE.prototype.setValue = function (val) {
        this.obj.value(val);
    };
    InputMDE.prototype.getForm = function () {
        return this.$el.parents('form').eq(0);
    };
    InputMDE.prototype.refresh = function(){
        this.watchObj.refresh();
    };
    return InputMDE;
})();


/**
 * Takes an arbitrary object, and determines the best Input class to represent it
 */
Memorable.inputFactory = function(obj) {
    if (obj.codemirror){
        return Memorable.InputMDE;
    } else {
        return Memorable.InputBasic;
    }
};

Memorable.items = [];

/**
 * Convenience method to find any classes decorated with `.memorable` and create a related Input object for it
 * @param selector - use to override the selector used to find all fields to be remembered
 */
Memorable.initialize = function(selector){
    Memorable.forget();
    var s = selector || '.memorable';
    $(s).each(function(){
        Memorable.add(this);
    });
};


/**
 * Forgets any successfully processed inputs from user
 */
Memorable.forget = function(key_prefix){
    key_prefix = key_prefix || $.cookie('memorable_forget');
    if (key_prefix) {
        for (var i = localStorage.length -1; i >=0; i--) {
            if(localStorage.key(i).indexOf(key_prefix) == 0){
                localStorage.removeItem(localStorage.key(i));
            }
        }
        $.removeCookie('memorable_forget', { path: '/', secure: top.location.protocol==='https:' ? true : false });
    }
};



/**
 * Creates a new Input object to remember changes to an individual field
 * @param obj - the raw object representing the field to be tracked
 */
Memorable.add = function(obj){
    var cls = Memorable.inputFactory(obj);
    Memorable.items.push(new Memorable.InputManager(new cls(obj)));
};


// Initialize
$(function(){Memorable.initialize();});
