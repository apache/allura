'use strict';

///////////////////////////////////////////////////
// Components for adding a new tool to a project //
///////////////////////////////////////////////////

/**
 * Add new tool button.
 * @constructor
 */
var ToggleAddNewTool = React.createClass({
    render: function() {
        let _this = this;

        var content = (() => {
            if (_this.props.showAddToolMenu) {
                return (
                    <div>
                        <span onClick={ _this.props.handleToggleAddNewTool }
                              className='add-tool-toggle'> + Add new...</span>
                        <NewToolMain />
                    </div>
                );
            } else {
                return (
                    <span onClick={ _this.props.handleToggleAddNewTool }
                          className='add-tool-toggle'> + Add new...</span>
                );
            }
        })();

        return (<li>
                {content}
            </li>
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
        value: React.PropTypes.func,
        errors: React.PropTypes.array
    },

    getErrors: function() {
        if (!this.props.errors.hasOwnProperty(this.props.id) || this.props.errors[this.props.id].length === 0) {
            return;
        }

        let errorList = [].concat(this.props.errors[this.props.id]);

        var result = errorList.map(function(e) {
            console.log('eeeee', e);
            console.dir(e);
            return <span>{e}</span>;
        });
        console.log('result', result);
        return (
            <div className="error-box">
                {result}
            </div>
        );
    },
    render: function () {
        let errors = this.getErrors();
        console.log('val e', errors);
        return (
            <div className="add-tool-field">
                <label htmlFor={this.props.id}>{this.props.label}</label>
                <input required
                       id={this.props.id}
                       onBlur={this.props.handleOnBlur}
                       onChange={this.props.handleOnChange}
                       value={this.props.value}/>

                {errors}
            </div>

        );
    }
});

var InstallNewToolForm = React.createClass({
    render: function() {
        return (
            <form id='add-tool-form'>
                <FormField
                    id="mount_label"
                    handleOnChange={this.props.handleChangeForm}
                    handleOnBlur={this.props.toolFormIsValid}
                    value={this.props.formData.mount_label}
                    label="Label"
                    errors={this.props.validationErrors}
                    />

                <FormField
                    id="mount_point"
                    handleOnChange={this.props.handleChangeForm}
                    handleOnBlur={this.props.toolFormIsValid}
                    value={this.props.formData.mount_point}
                    label="Url Path"
                    errors={this.props.validationErrors}
                />

                <div id={'add-tool-url-preview'}>
                    <p>
                        <small>{_getProjectUrl(false)}/</small>
                        <strong>{this.props.formData.mount_point}</strong>
                    </p>
                </div>
                <div>
                <button id='new-tool-submit'
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
        var titleStyle = {background: _getToolColor(this.props.toolLabel)};
        return (
            <div className='tool-info'>
                <div className='tool-info-left'>
                    <h1 style={titleStyle}>{this.props.toolLabel}</h1>
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
            errors: {
                mount_point: [],
                mount_label: []
            },
            new_tool: {
                mount_point: '',
                tool_label: '',
                mount_label: ''
            }
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
        console.log("HANDLE CHANGE -->", e.target.textContent);
        this._setActiveByLabel(e.target.textContent);
    },
    _setActiveByLabel: function(tool_label) {
        var index = this.state.installableTools.findIndex(
            x => x.tool_label === tool_label
        );
        console.log('index for tool_label: ', index);
        var active = this.state.installableTools[index];

        console.log('new active: ', active);

        var _new_tool = this.state.new_tool;
        console.log('new _new_tool: ', _new_tool);

        _new_tool.mount_label = active.defaults.default_mount_label;
        _new_tool.mount_point = '';

        this.setState({
            active: active,
            new_tool: _new_tool
        });
    },

    handleChangeForm: function(e) {
            var _new_tool = this.state.new_tool;
            _new_tool[e.target.id] = e.target.value;

            this.setState({
                new_tool: _new_tool
            });

        },

    handleSubmit: function(e) {
        e.preventDefault();
        var data = {
            _session_id: $.cookie('_session_id'),
            tool: this.state.active.name,
            mount_label: this.state.new_tool.mount_label,
            mount_point: this.state.new_tool.mount_point
        };

        $.ajax({
            type: 'POST',
            url: _getProjectUrl() + '/admin/install_tool/',
            data: data,
            success: function() {
                $('#messages')
                    .notify('Tool created', {
                        status: 'confirm'
                    });
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
        var errors = {
            mount_point: []
        };

        if (this.state.new_tool.mount_point.length < 3) {
            errors.mount_point.push('Mount point must have at least 3 characters.');
        }
        let data = {
            'mount_point': e.target.value,
            '_session_id': $.cookie('_session_id')
        };

        let result = $.post(_getProjectUrl() + '/admin/mount_point/', data);
        if (!result.responseJSON) {
            errors.mount_point.push('Mount point already exists.');
        }

        this.setState({errors: errors});

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
                        handleSubmit={this.handleSubmit}
                        handleChangeForm={this.handleChangeForm}
                        toolFormIsValid={this.toolFormIsValid}
                        validationErrors={this.state.errors}
                        handleAddButton={this.handleAddButton}/>
            </React.addons.CSSTransitionGroup>
    );
    }
});
