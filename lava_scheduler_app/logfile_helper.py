import cgi
import os
import re
import markup

def getDispatcherErrors(logfile):
    if not logfile:
        return "Log file is missing"
    errors = ""
    for line in logfile:
        if line.find("CriticalError:") != -1 or \
           line.find("Lava failed on test:") != -1 :
            errors += line

    return errors

def getDispatcherLogSize(logfile):
    if not logfile:
        return 0
    else:
        logfile.seek(0, os.SEEK_END)
        size = logfile.tell()
        return size

def getDispatcherLogMessages(logfile):
    if not logfile:
        return ('', "Log file is missing")

    logs = []
    log_prefix = '<LAVA_DISPATCHER>'
    level_pattern = re.compile('....-..-.. ..:..:.. .. ([A-Z]+):')
    for line in logfile:
        if not line.startswith(log_prefix):
            continue
        line = line[len(log_prefix):].strip()
        match = level_pattern.match(line)
        if not match:
            continue
        if len(line) > 90:
            line = line[:90] + '...'
        logs.append((match.group(1), line))
    return logs

def formatLogFileAsHtml(logfile):
    if not logfile:
        return "Log file is missing"


    sections = []
    cur_section_type = None
    cur_section = []

    for line in logfile:
        print repr(line)
        line = line.replace('\r', '')
        if not line:
            continue
        if line == 'Traceback (most recent call last):\n':
            sections.append((cur_section_type, cur_section))
            cur_section_type = 'traceback'
            cur_section = [line]
        elif cur_section_type == 'traceback':
            cur_section.append(line)
            if not line.startswith(' '):
                sections.append((cur_section_type, cur_section))
                cur_section_type = None
                cur_section = []
                continue
        elif line.find("<LAVA_DISPATCHER>") != -1 or \
           line.find("lava_dispatcher") != -1 or \
           line.find("CriticalError:") != -1 :
            if cur_section_type is None:
                cur_section_type = 'console'
            elif cur_section_type == 'log':
                sections.append((cur_section_type, cur_section))
                cur_section_type = 'console'
                cur_section = []
            cur_section.append(line)
        else:
            if cur_section_type is None:
                cur_section_type = 'log'
            elif cur_section_type == 'console':
                sections.append((cur_section_type, cur_section))
                cur_section_type = 'log'
                cur_section = []
            cur_section.append(line)
    if cur_section:
        sections.append((cur_section_type, cur_section))

    page = markup.page(mode="xml")


    page.init()

    for i in range(len(sections)):
        section_type, section = sections[i]
        page.a(name='entry' + str(i))
        page.a.close()
        if section_type == 'console':
            page.pre(cgi.escape(''.join(section)), class_='console_log')
        elif section_type == 'log':
            if len(section) > 20 and i < len(sections) - 1:
                page.a('skip %s lines to next log entry &rarr;' % len(section),
                       href='#entry' + str(i+1))
            page.pre(cgi.escape(''.join(section)), class_='dispatcher_log')
        elif section_type == 'traceback':
            page.pre(cgi.escape(''.join(section)), class_='traceback_log')
        else:
            page.pre(cgi.escape(''.join(section)), class_='other')

    return str(page)
    ##         pass
    ##         # close the previous log
    ##         if len(dispatcher_log) > 0:
    ##             dispatcher_log += line
    ##             if len(console_log) > 0:
    ##                 # dispatcher
    ##                 page.div(id="%d"%id_count, class_="dispatcher_log")
    ##                 page.a(name="%d"%id_count)
    ##                 page.pre()
    ##                 page.code(cgi.escape(dispatcher_log))
    ##                 page.pre.close()
    ##                 page.div.close()
    ##                 dispatcher_log = ""

    ##                 # console
    ##                 # collapse ?
    ##                 line_count = len(console_log.splitlines())
    ##                 if line_count > 20:
    ##                     page.div(id="%d"%id_count, class_="toggle_console_log")
    ##                     page.a(cgi.escape("<"*30+"- Jump to next <LAVA_DISPATCHER> and skip over %3d lines -"%line_count+">"*30), href="#%d"%(id_count+1), _class="toggle_console_log")
    ##                     page.div.close()

    ##                 page.div(id="%d"%id_count, class_="console_log")
    ##                 page.pre()
    ##                 page.code(cgi.escape(console_log))
    ##                 page.pre.close()
    ##                 page.div.close()
    ##                 console_log = ""
    ##         else:
    ##             id_count += 1
    ##             dispatcher_log = line
    ##     else:
    ##         console_log += line

    ## if len(dispatcher_log) > 0:
    ##     page.div(id="%d"%id_count, class_="dispatcher_log")
    ##     page.pre()
    ##     page.code(dispatcher_log)
    ##     page.pre.close()
    ##     page.div.close()

    ## if len(console_log) > 0:
    ##     # console
    ##     page.div(id="%d"%id_count, class_="console_log")
    ##     page.pre()
    ##     page.code(cgi.escape(console_log))
    ##     page.pre.close()
    ##     page.div.close()

    ## pp =  page.__str__()
    ## return pp

# for debugging
if __name__ == '__main__':
    file = open("/srv/lava/dev/var/www/lava-server/media/lava-logs/job-3020.log")
    print formatLogFileAsHtml(file)
