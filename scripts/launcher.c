// JARVIS.app ishga tushiruvchisi.
//
// Nega skript emas, kichik dastur: macOS mikrofon ruxsatini (TCC) ilovaga beradi. Python
// shu dasturning *bola jarayoni* sifatida ishga tushsa, ruxsat oynasida «JARVIS» chiqadi va
// Info.plist dagi NSMicrophoneUsageDescription ishlatiladi.
//
// Loyiha papkasi Contents/Resources/root faylidan o'qiladi; log: ~/Library/Logs/jarvis/app.log

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

static void alert(const char *msg) {
    char cmd[1024];
    snprintf(cmd, sizeof cmd,
             "osascript -e 'display alert \"JARVIS ishga tushmadi\" message \"%s\"'", msg);
    system(cmd);
}

int main(void) {
    char exe[PATH_MAX], real[PATH_MAX];
    uint32_t n = sizeof exe;
    if (_NSGetExecutablePath(exe, &n) != 0 || !realpath(exe, real)) return 1;

    // .../JARVIS.app/Contents/MacOS/JARVIS → .../JARVIS.app/Contents
    char contents[PATH_MAX];
    strncpy(contents, real, sizeof contents);
    for (int i = 0; i < 2; i++) {
        char *slash = strrchr(contents, '/');
        if (slash) *slash = '\0';
    }

    char rootfile[PATH_MAX], root[PATH_MAX] = {0};
    snprintf(rootfile, sizeof rootfile, "%s/Resources/root", contents);
    FILE *f = fopen(rootfile, "r");
    if (!f || !fgets(root, sizeof root, f)) {
        alert("Contents/Resources/root topilmadi. scripts/build-app.sh ni qayta ishga tushiring.");
        return 1;
    }
    fclose(f);
    root[strcspn(root, "\r\n")] = '\0';

    char python[PATH_MAX];
    snprintf(python, sizeof python, "%s/.venv/bin/python", root);
    if (access(python, X_OK) != 0) {
        alert(".venv topilmadi. Loyiha papkasida: python3 -m venv .venv && "
              ".venv/bin/pip install -e .[voice,app]");
        return 1;
    }
    if (chdir(root) != 0) return 1;  // .env shu papkadan o'qiladi

    char logdir[PATH_MAX], logfile[PATH_MAX];
    const char *home = getenv("HOME");
    snprintf(logdir, sizeof logdir, "%s/Library/Logs/jarvis", home ? home : "/tmp");
    mkdir(logdir, 0755);
    snprintf(logfile, sizeof logfile, "%s/app.log", logdir);

    posix_spawn_file_actions_t fa;
    posix_spawn_file_actions_init(&fa);
    posix_spawn_file_actions_addopen(&fa, STDOUT_FILENO, logfile, O_WRONLY | O_CREAT | O_APPEND, 0644);
    posix_spawn_file_actions_adddup2(&fa, STDOUT_FILENO, STDERR_FILENO);

    setenv("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", 1);
    setenv("PYTHONUNBUFFERED", "1", 1);

    char *argv[] = {python, "-m", "jarvis.app", NULL};
    if (posix_spawn(&child, python, &fa, NULL, argv, environ) != 0) {
        alert("Python'ni ishga tushirib bo'lmadi.");
        return 1;
    }
    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);

    int status = 0;
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
