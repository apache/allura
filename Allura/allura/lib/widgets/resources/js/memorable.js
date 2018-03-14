/*global $, SF, console, jQuery, localStorage */
window.SF = window.SF || {};
SF.Memorable = {};

/**
 * Class that describes the management of a memorable input - identifying, watching, saving, restoring, and forgetting.
 */
SF.Memorable.InputManager = (function(){

    /**
     * @param inputObj - the InputBasic or InputMDE object representing the input to be tracked
     * @constructor
     */
    function InputManager(inputObj){
        this.inputObj = inputObj;
        this.$form = this.inputObj.getForm();

        this.inputObj.watchObj.on(this.inputObj.watchEvent, this.handleSave.bind(this));

        this.forget();
        this.restore();
    }

    /**
     * Builds a unique key to use when persisting the input's value
     * @returns {string}
     */
    InputManager.prototype.getStorageKey = function(){
        function isUsableName($el){
            var name = $el.attr('name');
            if (name && name.length != 28){
                return true;
            }
        }
        function getRelativeAction($f){
            var action = $f[0].action;
            var list = action.split('/');
            var relativeAction = "";
            for (i = 3; i < list.length; i++) {
              relativeAction += "/";
              relativeAction += list[i];
            }
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
     * Event handler for invoke the safe
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

    /**
     * Forgets any successfully processed inputs from user
     */
    InputManager.prototype.forget = function(){
        var key_prefix = $.cookie('memorable_forget');
        if (key_prefix) {
            for (var i = localStorage.length -1; i >=0; i--) {
                if(localStorage.key(i).indexOf(key_prefix) == 0){
                    localStorage.removeItem(localStorage.key(i));
                }
            }
            $.removeCookie('memorable_forget', { path: '/' });
        }
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
SF.Memorable.InputBasic = (function() {
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
    return InputBasic;
})();


/**
 * Class describing a field backed by SimpleMDE, as identified by the passed instance of `SimpleMDE` provided, with specific methods for
 * getting & setting the value, and finding it's parent form
 *
 * @property obj: the SimpleMDE object describing the field to be tracked
 * @property watchEvent: the name of the event to watch to detect when changes have been made
 * @property watchObj: the object instance to watch for events on; editor.codemirror per their docs
 * @property $el: the jquery object representing the actual input field on the page
 */
SF.Memorable.InputMDE = (function() {
    /**
     * @param obj: A SimpleMDE object representing the input field
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
    return InputMDE;
})();


/**
 * Takes an arbitrary object, and determines the best Input class to represent it
 */
SF.Memorable.inputFactory = function(obj) {
    if (obj.codemirror){
        return SF.Memorable.InputMDE;
    } else {
        return SF.Memorable.InputBasic;
    }
};


/**
 * Convenience method to find any classes decorated with `.memorable` and create a related Input object for it
 * @param selector - use to override the selector used to find all fields to be remembered
 */
SF.Memorable.initialize = function(selector){
    var s = selector || '.memorable';
    SF.Memorable.items = [];
    $(s).each(function(){
        var cls = SF.Memorable.inputFactory(this);
        SF.Memorable.items.push(new SF.Memorable.InputManager(new cls(this)));
    });
};


/**
 * Creates a new Input object to remember changes to an individual field
 * @param obj - the raw object representing the field to be tracked
 */
SF.Memorable.add = function(obj){
    var cls = SF.Memorable.inputFactory(obj);
    SF.Memorable.items.push(new SF.Memorable.InputManager(new cls(obj)));
};


// Initialize
$(function(){SF.Memorable.initialize();});