/* SPDX-License-Identifier: ISC */
/*
 * Minimal readpassphrase(3), same semantics as the OpenBSD one.
 * musl has none and libbsd is not packaged. Only used to build shadow.
 */

#include <ctype.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

#include "readpassphrase.h"

static volatile sig_atomic_t rpp_signo[NSIG];

static void rpp_handler(int s)
{
	rpp_signo[s] = 1;
}

char *readpassphrase(const char *prompt, char *buf, size_t bufsiz, int flags)
{
	static const int sigs[] = { SIGALRM, SIGHUP, SIGINT, SIGPIPE, SIGQUIT,
				    SIGTERM, SIGTSTP, SIGTTIN, SIGTTOU };
	const size_t nsigs = sizeof(sigs) / sizeof(sigs[0]);
	struct sigaction sa, saved[sizeof(sigs) / sizeof(sigs[0])];
	struct termios term, oterm;
	int input, output, save_errno, need_restart;
	int have_term = 0;
	char *end, *p, *res;
	char ch;
	ssize_t nr;
	size_t i;

	if (bufsiz == 0) {
		errno = EINVAL;
		return NULL;
	}

restart:
	for (i = 0; i < NSIG; i++)
		rpp_signo[i] = 0;
	need_restart = 0;
	save_errno = 0;

	if ((flags & RPP_STDIN) ||
	    (input = output = open("/dev/tty", O_RDWR)) == -1) {
		if (flags & RPP_REQUIRE_TTY) {
			errno = ENOTTY;
			return NULL;
		}
		input = STDIN_FILENO;
		output = STDERR_FILENO;
	}

	/* No SA_RESTART: a signal must interrupt read(). */
	sigemptyset(&sa.sa_mask);
	sa.sa_flags = 0;
	sa.sa_handler = rpp_handler;
	for (i = 0; i < nsigs; i++)
		sigaction(sigs[i], &sa, &saved[i]);

	if (tcgetattr(input, &oterm) == 0) {
		have_term = 1;
		memcpy(&term, &oterm, sizeof(term));
		if (!(flags & RPP_ECHO_ON))
			term.c_lflag &= ~(ECHO | ECHONL);
		tcsetattr(input, TCSAFLUSH, &term);
	} else {
		have_term = 0;
	}

	if (!(flags & RPP_STDIN))
		(void)write(output, prompt, strlen(prompt));

	end = buf + bufsiz - 1;
	p = buf;
	while ((nr = read(input, &ch, 1)) == 1 && ch != '\n' && ch != '\r') {
		if (p < end) {
			if (flags & RPP_SEVENBIT)
				ch &= 0x7f;
			if (isalpha((unsigned char)ch)) {
				if (flags & RPP_FORCELOWER)
					ch = (char)tolower((unsigned char)ch);
				if (flags & RPP_FORCEUPPER)
					ch = (char)toupper((unsigned char)ch);
			}
			*p++ = ch;
		}
	}
	*p = '\0';
	save_errno = errno;
	res = (nr == -1) ? NULL : buf;

	if (have_term && !(term.c_lflag & ECHO))
		(void)write(output, "\n", 1);

	if (have_term)
		tcsetattr(input, TCSAFLUSH, &oterm);

	for (i = 0; i < nsigs; i++)
		sigaction(sigs[i], &saved[i], NULL);

	if (input != STDIN_FILENO)
		close(input);

	/* Re-deliver anything that arrived while echo was off. */
	for (i = 0; i < nsigs; i++) {
		if (rpp_signo[sigs[i]]) {
			kill(getpid(), sigs[i]);
			if (sigs[i] == SIGTSTP || sigs[i] == SIGTTIN ||
			    sigs[i] == SIGTTOU)
				need_restart = 1;
		}
	}
	if (need_restart)
		goto restart;

	if (res == NULL)
		errno = save_errno;
	return res;
}
