/* Both modules must consume a canceled request before the other owner releases
 * the native fence. A final Stock value alone can hide an unwanted activation. */
static void retry_case(const char *name,uint32_t first,uint32_t replacement) {
    uint32_t initial_status_calls=status_calls;
    conflict=1u;
    assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,first)==FX_OK);
    steps(160u);
    assert(busy_replies && !policy.requested && !atomic_load(&policy.effective));
    assert(!policy.transitions && status_calls>initial_status_calls);
    if(!strcmp(name,"retry-release")) {
        conflict=0u;steps(160u);
        assert(policy.requested==first && atomic_load(&policy.effective)==first);
        assert(policy.transitions==1u && row(2u).value==first);
    } else {
        /* Stop just after a rejected native selection. The queued event then
         * precedes the next module entry, including an immediate fence release. */
        uint32_t previous=busy_replies;
        for(uint32_t i=0u;i<160u && previous==busy_replies;++i)steps(1u);
        assert(busy_replies>previous);
        if(!strcmp(name,"retry-latest")) {
            assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,replacement)==FX_OK);
            assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,first)==FX_OK);
        }
        assert(fx_ui_route(&owner,2u,FX_INPUT_CHANGE,0u)==FX_OK);
        if(!strcmp(name,"retry-cancel-release"))conflict=0u;
        steps(160u);
        assert(!policy.requested && !atomic_load(&policy.effective));
        assert(!policy.transitions && row(2u).value==0u);
        conflict=0u;steps(160u);
        assert(!policy.requested && !atomic_load(&policy.effective));
        assert(!policy.transitions && row(2u).value==0u);
    }
    assert(fx_platform_stop(&owner,0u)==FX_OK);
    assert(!policy.owner && !atomic_load(&policy.effective) && !menu_attached);
}
