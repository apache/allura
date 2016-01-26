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
/* eslint camelcase: 0 */
'use strict';

class ContextMenu extends React.Component {
    constructor(props) {
        super(props);
    }

    componentWillMount() {
        let _this = this;
        var mount_point;
        $('body').on('click.contextMenu', function(evt) {
            /* the :not filter should've worked as a 2nd param to .on() instead of this,
             but clicks in the page gutter were being delayed for some reason */
            if ($(evt.target).is(':not(.contextMenu)')) {
                /* if clicking directly onto another gear, set it directly.
                 this is necessary since sometimes our jquery events seem to interfere with the react event
                 that is supposed to handle this kind of thing */
                if ($(evt.target).is('.config-tool')) {
                    mount_point = $(evt.target).next().data('mount-point');
                } else {
                    // no current option menu
                    mount_point = "";
                }
                _this.props.onOptionClick(mount_point);
            }
        });
    }

    componentWillUnmount() {
        $("body").off('click.contextMenu');  // de-register our specific click handler
    }

    render() {
        let _this = this;
        return (
            <div className="contextMenu">
                <ToolTip targetSelector='#top_nav_admin .contextMenu a'/>
                <ul>{
                    this.props.items.map(function(o, i) {
                        return (<li key={i}>
                            <a href={o.href}
                               className={_this.props.classes.concat([o.className]).join(' ')}
                               title={o.tooltip}>{o.text}</a>
                        </li>);
                    })}
                </ul>
            </div>
        );
    }
}

ContextMenu.propTypes = {
    classes: React.PropTypes.array,
    items: React.PropTypes.arrayOf(React.PropTypes.object).isRequired,
    onOptionClick: React.PropTypes.func.isRequired
};

ContextMenu.defaultProps = {
    classes: []
};
