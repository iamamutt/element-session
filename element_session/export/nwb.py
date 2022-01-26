import datetime
from uuid import uuid4

import pynwb

from . import session

try:
    import element_animal

    HAVE_ELEMENT_ANIMAL = True
except ModuleNotFoundError:
    HAVE_ELEMENT_ANIMAL = False
try:
    import element_lab

    HAVE_ELEMENT_LAB = True
except ModuleNotFoundError:
    HAVE_ELEMENT_LAB = False


def session_to_nwb(session_key: dict, subject_id=None):
    """Gather session- and subject-level metadata and use it to create an NWBFile.

    Parameters
    ----------
    session_key: dict,
        e.g.,
        {
            'subject': 'subject5',
            'session_datetime': datetime.datetime(2020, 5, 12, 4, 13, 7)
        }
    subject_id: str, optional
        Indicate subject_id if it cannot be inferred

    Returns
    -------
    pynwb.NWBFile

    mappings:
        Session::KEY -> NWBFile.session_id
        Session::session_note -> NWBFile.session_description
        Session::session_datetime -> NWBFile.session_start_time
        SessionExperimenter::experimenter -> NWBFile.experimenter

        subject.Subject::subject -> NWBFile.subject.subject_id
        subject.Subject::sex -> NWBFile.subject.sex

        lab.Lab::institution -> NWBFile.institution
        lab.Lab::lab_name -> NWBFile.lab
        lab.Lab::time_zone -> NWBFile.session_start_time.timezone

    """

    # ensure only one session key is entered
    session_key = (session.Session & session_key).fetch1("KEY")

    session_identifier = {
        k: v.isoformat() if isinstance(v, datetime.datetime) else v
        for k, v in session_key.items()
    }

    nwbfile_kwargs = dict(
        session_id="_".join(session_identifier.values()), identifier=str(uuid4()),
    )

    session_info = (session.Session & session_key).join(session.SessionNote, left=True).fetch1()

    nwbfile_kwargs.update(
        session_start_time=session_info["session_datetime"].astimezone(
            datetime.timezone.utc
        )
    )

    nwbfile_kwargs.update(session_description=session_info.get("session_note", ""))

    experimenters = (session.SessionExperimenter & session_key).fetch("experimenter")

    nwbfile_kwargs.update(experimenter=list(experimenters) or None)

    if HAVE_ELEMENT_ANIMAL and element_animal.subject.schema.is_activated():
        from element_animal.export.nwb import subject_to_nwb

        subject_key = subject.Subject & session_key

        nwbfile_kwargs.update(subject=subject_to_nwb(subject_key))

        if HAVE_ELEMENT_LAB and element_lab.lab.schema.is_activated():
            lab_query = lab.Lab & subject.Subject.Lab() & session_key
            if lab_query:
                try:
                    lab_record = lab_query.fetch1()
                    nwbfile_kwargs.update(
                        institution=lab_record.get("institution"),
                        lab=lab_record.get("lab_name"),
                    )

                    # if timezone is present, localize session_start_time, which is in UTC be default
                    if (
                        "time_zone" in lab_record
                        and lab_record["time_zone"][:3] == "UTC"
                    ):
                        hours = int(lab_record["time_zone"][3:])
                        hours_timedelta = timedelta(hours=hours)
                        nwbfile_kwargs["session_start_time"].astimezone(
                            timezone(hours_timedelta)
                        )
                except DataJointError:
                    raise DataJointError(
                        "Multiple labs associated with this session. Try restricting your session key to specify lab."
                    )

    else:
        if subject_id is None:
            raise ValueError(
                "If you are not using element_animal, you musts specify a subject_id."
            )
        nwbfile_kwargs.update(subject=pynwb.file.Subject(subject_id=subject_id))

    return pynwb.NWBFile(**nwbfile_kwargs)
