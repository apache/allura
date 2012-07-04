from mock import Mock
from allura.model import VotableArtifact


class TestVotableArtifact(object):

    def setUp(self):
        self.user1 = Mock()
        self.user1.username = 'test-user'
        self.user2 = Mock()
        self.user2.username = 'user2'
        # monkey-patch vote properties for test
        VotableArtifact.votes_up = 0
        VotableArtifact.votes_down = 0
        VotableArtifact.votes_up_users = 0
        VotableArtifact.votes_down_users = 0

    def test_vote_up(self):
        vote = VotableArtifact()

        vote.vote_up(self.user1)
        assert vote.votes_up == 1
        assert vote.votes_up_users == [self.user1.username]

        vote.vote_up(self.user1)
        assert vote.votes_up == 1, 'Same user can vote only once'
        assert vote.votes_up_users == [self.user1.username]

        vote.vote_up(self.user2)
        assert vote.votes_up == 2
        assert vote.votes_up_users == [self.user1.username,
                                       self.user2.username]

        assert vote.votes_down == 0, 'vote_down must be 0 if we voted up only'
        assert not vote.votes_down_users

    def test_vote_down(self):
        vote = VotableArtifact()

        vote.vote_down(self.user1)
        assert vote.votes_down == 1
        assert vote.votes_down_users == [self.user1.username]

        vote.vote_down(self.user1)
        assert vote.votes_down == 1, 'Same user can vote only once'
        assert vote.votes_down_users == [self.user1.username]

        vote.vote_down(self.user2)
        assert vote.votes_down == 2
        assert vote.votes_down_users == [self.user1.username,
                                        self.user2.username]

        assert vote.votes_up == 0, 'vote_up must be 0 if we voted down only'
        assert not vote.votes_up_users

    def test_change_vote(self):
        vote = VotableArtifact()

        vote.vote_up(self.user1)
        vote.vote_down(self.user1)

        assert vote.votes_down == 1
        assert vote.votes_down_users == [self.user1.username]
        assert vote.votes_up == 0
        assert not vote.votes_up_users
