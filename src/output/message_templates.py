"""Message template functions for OutputFormatter."""


def _get_message_templates(self, language: str) -> dict:
    """Get message templates for the specified language."""
    if language == 'german':
        return {
            'code_review_intro': "Hey, ich brauche eure Hilfe fuer *2 Code Reviews* fuer: *{title}*",
            'testing_intro': "Hey, ich brauche eure Hilfe fuer *2 manuelle Tests* fuer: *{title}*",
            'ready_to_merge_intro': "Hey, diese PR ist jetzt bereit zum Mergen: *{title}*",
            'trade_offer': "Wie immer tausche ich gerne Reviews :smile:",
            'thanks': "Danke fuer die Reviews! :tada:",
            'pr_summary_header': "Ein kurzes Update zu meinen offenen PRs:",
            'pr_summary_in_review': "In Review",
            'pr_summary_ready_to_merge': "Ready to Merge",
            'pr_summary_in_progress': "In Progress",
            'pr_summary_footer': "",
            # Personalized messages for "My PRs for [author]"
            'personalized_code_review': "Hey {display_name}, ich brauche deine Hilfe fuer *ein Code Review* fuer: *{title}*",
            'personalized_testing': "Hey {display_name}, ich brauche deine Hilfe fuer *einen manuellen Test* fuer: *{title}*",
            'personalized_trade_offer': "Wie immer tausche ich gerne Reviews :smile:"
        }
    else:  # english (default)
        return {
            'code_review_intro': "Hey everyone, I need your help for *2 code reviews* on: *{title}*",
            'testing_intro': "Hey everyone, I need your help for *2 manual tests* on: *{title}*",
            'ready_to_merge_intro': "Hey everyone, this PR is now ready to merge: *{title}*",
            'trade_offer': "As always, I am happy to trade reviews :smile:",
            'thanks': "Thanks for the reviews! :tada:",
            'pr_summary_header': "A short update regarding my open PRs:",
            'pr_summary_in_review': "In Review",
            'pr_summary_ready_to_merge': "Ready to Merge",
            'pr_summary_in_progress': "In Progress",
            'pr_summary_footer': "Any help is appreciated! :smile:",
            # Personalized messages for "My PRs for [author]"
            'personalized_code_review': "Hey {display_name}, I need your help for *a code review* on: *{title}*",
            'personalized_testing': "Hey {display_name}, I need your help for *a manual test* on: *{title}*",
            'personalized_trade_offer': "As always, I am happy to trade reviews :smile:"
        }


def _generate_pr_summary_message(self, my_open_prs: list) -> str:
    """Generate a Slack message summarizing all open PRs categorized by status."""
    templates = self._get_message_templates(self.pr_summary_language)

    in_review = []
    ready_to_merge = []
    in_progress = []

    for pr in my_open_prs:
        labels = [label.lower() for label in pr.get('labels', [])]
        project_states = [state.lower() for state in pr.get('project_states', [])]

        # Ready to merge: label "ready to merge" OR project state "developer approved"/"maintainer approved"
        if ('ready to merge' in labels or
            'developer approved' in project_states or
            'maintainer approved' in project_states):
            ready_to_merge.append(pr)
        # In review: label "ready for review" OR project state "ready for review"
        elif ('ready for review' in labels or
              'ready for review' in project_states):
            in_review.append(pr)
        # Default: in progress
        else:
            in_progress.append(pr)

    # Build message with sections for each category
    message = templates['pr_summary_header'] + "\n\n"

    for prs, template_key in [
        (in_review, 'pr_summary_in_review'),
        (ready_to_merge, 'pr_summary_ready_to_merge'),
        (in_progress, 'pr_summary_in_progress')
    ]:
        if prs:
            message += f"`{templates[template_key]}`\n"
            for pr in prs:
                slack_title = pr['title'].replace('`', '')
                message += f"\u2022 {slack_title} - {pr['url']} (+{pr['additions']:,}/-{pr['deletions']:,} lines)\n"
            message += "\n"

    message += templates['pr_summary_footer']
    return message
