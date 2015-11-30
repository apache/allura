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
'use strict';

///////////////////////////////////////////////////
// Components for adding a new tool to a project //
///////////////////////////////////////////////////

/**
 * Add new tool button.
 * @constructor
 */
var AddNewToolButton = React.createClass({
    render: function() {
        return (
            <div>
            <a onClick={ this.props.handleToggleAddNewTool } className='add-tool-toggle'>
                Add New...
            </a>
            { this.props.showAddToolMenu && <NewToolMain {...this.props} />}
            </div>
        );
    }
});

/**
 * Menu for adding a new tool.
 * @constructor
 */
var NewToolMenu = React.createClass({
    propTypes: {
        tools: React.PropTypes.array,
        onPushAddButton: React.PropTypes.func,
        onSetActive: React.PropTypes.func,
        formData: React.PropTypes.object,
        visible: React.PropTypes.bool
    },
    render: function() {
        var _this = this;
        var showInfo = this.props.active.name !== 'Add a tool';
        var tools = this.props.tools.map(function(tool, i) {
            var classes;
            if (_this.props.active && _this.props.active.tool_label === tool.tool_label) {
                classes = ' selected-tool';
            }else {
                classes = ' ';
            }
            return (
                <div className={classes}
                    id={'add-new-' + tool.name}
                    key={`new-tool-btn-${i}`}
                    onClick={_this.props.handleChangeTool}>
                    {tool.tool_label}
                </div>
            );
        });

        return (
            <div className='tool-card'>
                <div className='box-title'>Add a new ...</div>
                <div id='installable-items'>
                    <div className='installable-tool-box'>
                        {tools}
                    </div>
                </div>
                {showInfo &&
                <NewToolInfo {...this.props}
                    name={this.props.active.name}
                    toolLabel={this.props.active.tool_label}
                    description={this.props.active.description}
                    handleAddButton={this.props.handleAddButton}/>
                }
            </div>
        );
    }
});

var FormField = React.createClass({
    propTypes: {
        id: React.PropTypes.string,
        handleOnChange: React.PropTypes.func,
        inputType: React.PropTypes.string,
        pattern: React.PropTypes.string,
        value: React.PropTypes.string,
        errors: React.PropTypes.object
    },
    getDefaultProps: function () {
        return {
            inputType: "text",
            pattern: "",
            errors: {}
        };
    },
    getErrors: function() {
        if (!this.props.errors.hasOwnProperty(this.props.id)
            || this.props.errors[this.props.id].length === 0) {
            return;
        }

        let errorList = [].concat(this.props.errors[this.props.id]);

        var result = errorList.map(function(error_list, i) {
            return <span key={"error-" + i}>{error_list}</span>;
        });
        console.log('result', result);
        return (
            <div className="add-tool-error-box">
                {result}
            </div>
        );
    },
    render: function () {
        let errors = this.getErrors();
        return (
            <div className="add-tool-field">
                <label className="tool-form-input" htmlFor={this.props.id}>{this.props.label}</label>
                <input type={this.props.inputType} required
                       id={this.props.id}
                       pattern={this.props.pattern}
                       onBlur={this.props.handleOnBlur}
                       onChange={this.props.handleOnChange}
                       value={this.props.value}/>

                {errors}
            </div>

        );
    }
});

var InstallNewToolForm = React.createClass({
        getDefaultProps: function () {
        return {
            canSubmit: false
        };
    },
    render: function() {
        return (
            <form id='add-tool-form'>
                <FormField
                    key="new-tool-mount-label"
                    id="mount_label"
                    handleOnChange={this.props.handleChangeForm}
                    handleOnBlur={this.props.toolFormIsValid}
                    value={this.props.formData.mount_label}
                    label="Label"
                    errors={this.props.validationErrors}
                    />

                <FormField
                    key="new-tool-mount-point"
                    id="mount_point"
                    handleOnChange={this.props.handleChangeForm}
                    handleOnBlur={this.props.toolFormIsValid}
                    value={this.props.formData.mount_point}
                    label="Url Path"
                    errors={this.props.validationErrors}
                />

                {this.props.toolLabel ===  'External Link' &&
                    <FormField
                        key="external-url-field"
                        id="options_url"
                        handleOnChange={this.props.handleChangeForm}
                        value={this.props.formData.options.options_url}
                        label="External Url"
                        pattern="https?://.+"
                        inputType="url"
                    />
                }
                <div id={'add-tool-url-preview'}>
                    <p>
                        <small>{_getProjectUrl(false)}/</small>
                        <strong>{this.props.formData.mount_point}</strong>
                    </p>
                </div>
                <div>
                <button disabled={!this.props.canSubmit} id='new-tool-submit'
                        onClick={this.props.handleSubmit}
                        className='add-tool-button'>
                    Add Tool
                </button>
                </div>
            </form>
        );
    }
});

var NewToolInfo = React.createClass({
    propTypes: {
        name: React.PropTypes.string,
        description: React.PropTypes.string,
        handleAddButton: React.PropTypes.func
    },

    render: function() {
        return (
            <div className='tool-info'>
                <div className='tool-info-left'>
                    <h1 className={this.props.toolLabel.toLowerCase() + "-tool"}>{this.props.toolLabel}</h1>
                    <p>{this.props.description}</p>
                </div>
                <div className='tool-info-right'>
                    <InstallNewToolForm {...this.props} />
                </div>
            </div>
        );
    }
});

var installableToolsCache = {};
function loadTools(id, callback) {
    if (!installableToolsCache[id]) {
        installableToolsCache[id] = $.get(_getProjectUrl(true) + '/admin/installable_tools/').promise();
    }
    installableToolsCache[id].done(callback);
}

var NewToolMain = React.createClass({
    getInitialState: function() {
        let toolPlaceHolder = {
            name: 'Add a tool',
            tool_label: 'Add a tool',
            description: 'click on one of the tools shown above to add it to your project.'
        };

        return {
            visible: false,
            installableTools: [toolPlaceHolder],
            active: toolPlaceHolder,
            canSubmit: false,
            errors: {
                mount_point: [],
                mount_label: []
            },
            new_tool: {
                mount_point: '',
                tool_label: '',
                mount_label: '',
                options: {}
            }
        };
    },
    getDefaultProps: function () {
        return {
            existingMounts: []
        };
    },
    componentDidMount: function() {
        let tools = loadTools('tools', function(result) {
            if (this.isMounted()) {
                this.setState({
                    installableTools: result.tools
                });
            }
        }.bind(this));
    },
    handleChangeTool: function(e) {
        this._setActiveByLabel(e.target.textContent);
    },
    _setActiveByLabel: function(tool_label) {
        var index = this.state.installableTools.findIndex(
            x => x.tool_label === tool_label
        );
        var active = this.state.installableTools[index];
        var _new_tool = this.state.new_tool;

        _new_tool.mount_label = active.defaults.default_mount_label;
        _new_tool.mount_point = '';
        _new_tool.options = {};

        this.setState({
            active: active,
            new_tool: _new_tool
        });
    },

    handleChangeForm: function(e) {
            var _new_tool = this.state.new_tool;
            var field_id = e.target.id;
            _new_tool[field_id] = e.target.value;
        if(field_id !== 'mount_point' && field_id !== 'mount_label'){
            _new_tool.options[field_id] = e.target.value;
        }
            this.setState({
                new_tool: _new_tool
            });
        },

    getOption: function(option_id){
        return option_id.split('options_').slice(-1)[0];
    },

    enableButton: function () {
      this.setState({
        canSubmit: true
      });
        console.log("enabledButton hit");
    },
    disableButton: function () {
      this.setState({
        canSubmit: false
      });
    },
    handleSubmit: function(e) {
        e.preventDefault();
        var _this = this;
        var data = {
            _session_id: $.cookie('_session_id'),
            tool: this.state.active.name,
            mount_label: this.state.new_tool.mount_label,
            mount_point: this.state.new_tool.mount_point,
        };

        if(this.state.active.name === 'link'){
            let options = this.state.new_tool.options;
            for(let k of Object.keys(options)){
                if(k.startsWith('options_')) {
                    data[this.getOption(k)] = options[k];
                }
            }
        }
        $.ajax({
            type: 'POST',
            url: _getProjectUrl() + '/admin/install_tool/',
            data: data,
            success: function() {
                $('#messages')
                    .notify('Tool created', {
                        status: 'confirm'
                    });
                _this.disableButton();
            },

            error: function() {
                $('#messages')
                    .notify('Error creating tool.', {
                        status: 'error'
                    });
            }
        });
    },
    toolFormIsValid: function(e) {
        e.preventDefault();
        if(!e.target.value){
            return
        }
        var errors = {
            mount_point: []
        };

        if (this.state.new_tool.mount_point.length < 3) {
            errors.mount_point.push('Mount point must have at least 3 characters.');
        }
        if (this.props.existingMounts.indexOf(e.target.value) !== -1) {
            errors.mount_point.push('Mount point already exists.');
        }
        if (errors) {
            this.setState({errors: errors});
        } else {
            this.enableButton();

        }

    },

    render: function() {
        return (
            <React.addons.CSSTransitionGroup
                transitionName="menu"
                transitionEnterTimeout={500}
                transitionLeaveTimeout={300} >
                    <NewToolMenu
                        active={this.state.active}
                        tools={this.state.installableTools}
                        formData={this.state.new_tool}
                        handleChangeTool={this.handleChangeTool}
                        canSubmit={this.state.canSubmit}
                        handleSubmit={this.handleSubmit}
                        handleChangeForm={this.handleChangeForm}
                        toolFormIsValid={this.toolFormIsValid}
                        validationErrors={this.state.errors}
                        handleAddButton={this.handleAddButton}/>
            </React.addons.CSSTransitionGroup>
    );
    }
});
