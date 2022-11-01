#       Licensed to the Apache Software Foundation (ASF) under one
#       or more contributor license agreements.  See the NOTICE file
#       distributed with this work for additional information
#       regarding copyright ownership.  The ASF licenses this file
#       to you under the Apache License, Version 2.0 (the
#       "License"); you may not use this file except in compliance
#       with the License.  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#       Unless required by applicable law or agreed to in writing,
#       software distributed under the License is distributed on an
#       "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
#       KIND, either express or implied.  See the License for the
#       specific language governing permissions and limitations
#       under the License.

from mock import Mock
from allura.model import VotableArtifact


class TestVotableArtifact:

    def setup_method(self, method):
        self.user1 = Mock()
        self.user1.username = 'test-user'
        self.user2 = Mock()
        self.user2.username = 'user2'

    def test_vote_up(self):
        vote = VotableArtifact()

        vote.vote_up(self.user1)
        assert vote.votes_up == 1
        assert vote.votes_up_users == [self.user1.username]

        vote.vote_up(self.user2)
        assert vote.votes_up == 2
        assert vote.votes_up_users == [self.user1.username,
                                       self.user2.username]

        vote.vote_up(self.user1)  # unvote user1
        assert vote.votes_up == 1
        assert vote.votes_up_users == [self.user2.username]

        assert vote.votes_down == 0, 'vote_down must be 0 if we voted up only'
        assert len(vote.votes_down_users) == 0

    def test_vote_down(self):
        vote = VotableArtifact()

        vote.vote_down(self.user1)
        assert vote.votes_down == 1
        assert vote.votes_down_users == [self.user1.username]

        vote.vote_down(self.user2)
        assert vote.votes_down == 2
        assert vote.votes_down_users == [self.user1.username,
                                         self.user2.username]

        vote.vote_down(self.user1)  # unvote user1
        assert vote.votes_down == 1
        assert vote.votes_down_users == [self.user2.username]

        assert vote.votes_up == 0, 'vote_up must be 0 if we voted down only'
        assert len(vote.votes_up_users) == 0

    def test_change_vote(self):
        vote = VotableArtifact()

        vote.vote_up(self.user1)
        vote.vote_down(self.user1)

        assert vote.votes_down == 1
        assert vote.votes_down_users == [self.user1.username]
        assert vote.votes_up == 0
        assert len(vote.votes_up_users) == 0

    def test_json(self):
        vote = VotableArtifact()
        assert vote.__json__() == {'votes_up': 0, 'votes_down': 0}

        vote.vote_down(self.user1)
        assert vote.__json__() == {'votes_up': 0, 'votes_down': 1}

        vote.vote_up(self.user2)
        assert vote.__json__() == {'votes_up': 1, 'votes_down': 1}
